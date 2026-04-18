from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from axelo.config import settings
from axelo.engine.models import RequirementSheet
from axelo.engine.principal import IntakeAIProcessor
from axelo.engine.runtime import UnifiedEngine
from axelo.models.contracts import MissionContract
from axelo.utils.session_catalog import SessionCatalog, session_dir_for_id
from axelo.web.contracts import CheckpointRecord
from axelo.web.engine_hook import attach_web_hook
from axelo.web.services.intake_service import _evict_stale_sessions, _intake_sessions, _save_intake_session, _sessions_lock, _run_mission
from axelo.web.services.workbench_service import (
    build_artifact_refs,
    build_run_view,
    build_session_summary,
    build_session_view,
    list_workbench_sessions,
    load_checkpoints,
    load_intake_session,
    load_run_events,
    save_checkpoint_resolution,
)

router = APIRouter(prefix="/api")


class SessionMessageRequest(BaseModel):
    message: str


class CheckpointResolutionRequest(BaseModel):
    approved: bool


@router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    return list_workbench_sessions()


@router.post("/sessions")
async def create_session() -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    contract = MissionContract(contract_id=session_id)
    session: dict[str, Any] = {
        "intake_id": session_id,
        "contract": contract,
        "history": [],
        "phase": "welcome",
        "session_id": "",
        "run_ids": [],
        "created_at": datetime.now().isoformat(),
    }
    async with _sessions_lock:
        _evict_stale_sessions()
        _intake_sessions[session_id] = session
    _save_intake_session(session_id, session)
    return build_session_summary(session).model_dump(mode="json")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session_view = build_session_view(session_id)
    if session_view is not None:
        return session_view.model_dump(mode="json")
    return _get_legacy_run_detail(session_id)


@router.get("/sessions/{session_id}/thread")
async def get_session_thread(session_id: str) -> dict[str, Any]:
    session_view = build_session_view(session_id)
    if session_view is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {
        "session_id": session_view.session_id,
        "current_run_id": session_view.current_run_id,
        "items": [item.model_dump(mode="json") for item in session_view.thread_items],
    }


@router.post("/sessions/{session_id}/messages")
async def post_session_message(session_id: str, req: SessionMessageRequest) -> dict[str, Any]:
    session = load_intake_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    processor = IntakeAIProcessor()
    history = [{"role": turn.get("role", ""), "content": turn.get("content", "")} for turn in session.get("history", [])]
    contract_payload = session.get("contract") or {}
    contract = contract_payload if isinstance(contract_payload, MissionContract) else MissionContract.model_validate(contract_payload)
    result = await processor.process_message(req.message, contract, history)

    turn_id = str(uuid.uuid4())
    history_items = session.get("history", [])
    history_items.append({"role": "user", "content": req.message, "turn_id": turn_id, "ts": datetime.now().isoformat()})
    history_items.append({"role": "assistant", "content": result["ai_reply"], "turn_id": f"{turn_id}_reply", "ts": datetime.now().isoformat()})
    session["history"] = history_items
    session["contract"] = result["updated_contract"]
    session["phase"] = "contract_ready" if result["readiness"].is_ready else "discussing"
    _intake_sessions[session_id] = session
    _save_intake_session(session_id, session)

    session_view = build_session_view(session_id)
    return {
        "session": session_view.model_dump(mode="json") if session_view else {},
        "ai_reply": result["ai_reply"],
        "contract": result["updated_contract"].model_dump(mode="json"),
        "readiness": result["readiness"].model_dump(mode="json"),
    }


@router.post("/sessions/{session_id}/runs")
async def create_run(session_id: str, request: Request) -> dict[str, Any]:
    session = load_intake_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    contract_payload = session.get("contract") or {}
    contract = contract_payload if isinstance(contract_payload, MissionContract) else MissionContract.model_validate(contract_payload)
    readiness = contract.readiness_assessment
    if not readiness.is_ready:
        raise HTTPException(status_code=400, detail=f"Session '{session_id}' is not ready to run.")

    running_tasks: dict[str, asyncio.Task] = request.app.state.running_tasks
    active_run_ids = set(running_tasks.keys())
    for run_id in session.get("run_ids", []):
        if run_id in active_run_ids:
            raise HTTPException(status_code=409, detail="An active run already exists for this session.")

    rs_kwargs = contract.to_requirement_sheet_kwargs()
    requirement_sheet = RequirementSheet(**rs_kwargs)
    engine = UnifiedEngine()
    prepared = await engine.plan_request(
        prompt=requirement_sheet.to_prompt(),
        url=contract.target_url,
        goal=contract.objective,
        metadata={
            "requirements": requirement_sheet.to_metadata(),
            "contract": contract.model_dump(mode="json"),
            "intake_id": session_id,
            "session_id": session_id,
        },
    )
    prepared.contract = contract

    broadcaster = request.app.state.broadcaster
    attach_web_hook(engine, broadcaster, prepared.session_id)
    request.app.state.live_sessions.add(prepared.session_id)
    task = asyncio.create_task(_run_mission(engine, prepared, broadcaster), name=f"workbench_run:{prepared.session_id}")
    running_tasks[prepared.session_id] = task
    request.app.state.last_session_id = prepared.session_id

    def _cleanup(_task: asyncio.Task, *, run_id: str = prepared.session_id) -> None:
        running_tasks.pop(run_id, None)
        request.app.state.live_sessions.discard(run_id)

    task.add_done_callback(_cleanup)

    session.setdefault("run_ids", [])
    session["run_ids"] = [*session["run_ids"], prepared.session_id]
    session["session_id"] = prepared.session_id
    session["phase"] = "executing"
    contract.locked_at = datetime.now().isoformat()
    contract.session_id = prepared.session_id
    session["contract"] = contract
    _intake_sessions[session_id] = session
    _save_intake_session(session_id, session)

    return {
        "session_id": session_id,
        "run": build_run_view(prepared.session_id, session_id=session_id).model_dump(mode="json"),
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    return build_run_view(run_id).model_dump(mode="json")


@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: str, cursor: int = 0) -> dict[str, Any]:
    events = load_run_events(run_id, cursor=cursor)
    return {
        "run_id": run_id,
        "events": [event.model_dump(mode="json") for event in events],
        "next_cursor": events[-1].seq if events else cursor,
    }


@router.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict[str, Any]:
    return {"run_id": run_id, "artifacts": [item.model_dump(mode="json") for item in build_artifact_refs(run_id)]}


@router.get("/runs/{run_id}/checkpoints")
async def get_run_checkpoints(run_id: str) -> dict[str, Any]:
    checkpoints = load_checkpoints(run_id)
    return {"run_id": run_id, "checkpoints": [item.model_dump(mode="json") for item in checkpoints]}


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/approve")
async def approve_checkpoint(run_id: str, checkpoint_id: str) -> dict[str, Any]:
    record = save_checkpoint_resolution(run_id, checkpoint_id, True)
    return {"run_id": run_id, "checkpoint": record.model_dump(mode="json")}


@router.post("/runs/{run_id}/checkpoints/{checkpoint_id}/reject")
async def reject_checkpoint(run_id: str, checkpoint_id: str) -> dict[str, Any]:
    record = save_checkpoint_resolution(run_id, checkpoint_id, False)
    return {"run_id": run_id, "checkpoint": record.model_dump(mode="json")}


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, request: Request) -> dict[str, Any]:
    running_tasks: dict[str, asyncio.Task] = request.app.state.running_tasks
    return {
        "run_id": run_id,
        "active": run_id in running_tasks,
        "checkpoints": [item.model_dump(mode="json") for item in load_checkpoints(run_id)],
    }


@router.get("/sessions/{session_id}/events")
async def get_session_events(session_id: str, since_line: int = 0) -> dict[str, Any]:
    events = load_run_events(session_id, cursor=since_line)
    if events:
        return {"events": [event.model_dump(mode="json") for event in events], "next_line": events[-1].seq}

    session_dir = _find_session_dir(Path(settings.workspace) / "sessions", session_id)
    if not session_dir:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    events_path = session_dir / "logs" / "events.jsonl"
    if not events_path.exists():
        return {"events": [], "next_line": since_line}

    lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_lines = lines[since_line:]
    legacy_events: list[dict[str, Any]] = []
    for line in new_lines:
        line = line.strip()
        if not line:
            continue
        try:
            legacy_events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"events": legacy_events, "next_line": since_line + len(new_lines)}


def _get_legacy_run_detail(run_id: str) -> dict[str, Any]:
    sessions_dir = Path(settings.workspace) / "sessions"
    session_dir = _find_session_dir(sessions_dir, run_id)
    if not session_dir:
        raise HTTPException(status_code=404, detail=f"Session '{run_id}' not found.")

    summary = _read_session_summary(session_dir) or {}
    principal_state = _read_json(session_dir / "logs" / "principal_state.json")
    mission_report = _read_json(session_dir / "artifacts" / "final" / "mission_report.json")
    artifact_index = _read_json(session_dir / "artifacts" / "final" / "artifact_index.json")
    request_payload = _read_json(session_dir / "session_request.json")

    return {
        **summary,
        "request": request_payload,
        "principal_state": principal_state,
        "mission_report": mission_report,
        "artifact_index": artifact_index,
    }


def _find_session_dir(sessions_dir: Path, session_id: str) -> Path | None:
    candidate = session_dir_for_id(sessions_dir, session_id)
    if candidate.is_dir():
        return candidate
    if not sessions_dir.exists():
        return None
    for site_dir in sessions_dir.iterdir():
        if not site_dir.is_dir():
            continue
        fallback = site_dir / session_id
        if fallback.is_dir():
            return fallback
    return None


def _read_session_summary(session_dir: Path) -> dict[str, Any] | None:
    request_payload = _read_json(session_dir / "session_request.json")
    if request_payload is None:
        return None
    mission_report = _read_json(session_dir / "artifacts" / "final" / "mission_report.json") or {}
    site_manifest = _read_json(session_dir.parent / "site.json") or {}
    metadata = request_payload.get("metadata") if isinstance(request_payload.get("metadata"), dict) else {}
    site_key = str(mission_report.get("site_key") or site_manifest.get("site_key") or metadata.get("site_key") or "")
    return {
        "session_id": session_dir.name,
        "site_code": session_dir.parent.name,
        "site_key": site_key or session_dir.parent.name,
        "url": request_payload.get("url", ""),
        "goal": request_payload.get("goal") or request_payload.get("effective_goal", ""),
        "status": mission_report.get("mission_status", "unknown"),
        "outcome": mission_report.get("mission_outcome", "unknown"),
        "success": mission_report.get("success", False),
        "session_dir": str(session_dir),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    return None
