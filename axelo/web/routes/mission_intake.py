from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from axelo.engine.models import RequirementSheet
from axelo.engine.principal import IntakeAIProcessor
from axelo.engine.runtime import UnifiedEngine
from axelo.models.contracts import MissionContract
from axelo.web.engine_hook import attach_web_hook
from axelo.web.services.intake_service import (
    _intake_sessions,
    _sessions_lock,
    _evict_stale_sessions,
    _save_intake_session,
    _auto_analyse,
    _build_requirement_sheet,
    _sanitized_web_intake,
    _run_mission,
)

log = structlog.get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    message: str
    role: str = "user"


class AnnotationRequest(BaseModel):
    message: str
    annotation_type: str = "clarification"  # "clarification" | "correction" | "note"


class IntakeChatResponse(BaseModel):
    intake_id: str
    turn_id: str
    phase: str
    ai_reply: str
    contract: MissionContract
    readiness: Any  # ReadinessAssessment
    contract_delta: dict[str, Any]


class MissionRequest(BaseModel):
    url: str
    scope: str = "domain"
    login_required: bool = False

    data_type: str = "custom"
    goal: str = ""
    key_fields: list[str] = Field(default_factory=list)
    target_records: int = 100
    sample_size: int = 10

    auth_mechanism: str = "auto"
    stealth: str = "medium"
    js_rendering: str = "auto"

    max_pages: int = 50
    requests_per_sec: float = 2.0
    concurrency: int = 3
    timeout_sec: int = 30
    retry: bool = True
    verify: bool = True

    budget_usd: float = 5.0
    time_limit_min: int = 30

    output_format: str = "sdk"
    dedup: bool = True
    session_label: str = ""

    username: str = ""
    password: str = ""


class MissionResponse(BaseModel):
    session_id: str
    site_code: str
    site_key: str
    status: str
    message: str
    effective_goal: str
    auto_analysis: dict[str, Any] | None = None


class MissionStopRequest(BaseModel):
    session_id: str = ""


# ---------------------------------------------------------------------------
# Intake routes
# ---------------------------------------------------------------------------

@router.post("/api/intake/session")
async def create_intake_session() -> dict[str, Any]:
    """Create a new intake session. Returns intake_id."""
    intake_id = str(uuid.uuid4())
    contract = MissionContract(contract_id=intake_id)
    session: dict[str, Any] = {
        "intake_id": intake_id,
        "contract": contract,
        "history": [],
        "phase": "welcome",
        "session_id": "",
        "run_ids": [],
        "created_at": datetime.now().isoformat(),
    }
    async with _sessions_lock:
        _evict_stale_sessions()
        _intake_sessions[intake_id] = session
    _save_intake_session(intake_id, session)
    log.info("intake_session_created", intake_id=intake_id)
    return {"intake_id": intake_id, "phase": "welcome", "created_at": session["created_at"]}


@router.post("/api/intake/{intake_id}/chat")
async def intake_chat(intake_id: str, req: ChatMessageRequest) -> IntakeChatResponse:
    """Send a user message. AI processes it, updates contract, returns new state."""
    session = _intake_sessions.get(intake_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Intake session '{intake_id}' not found.")

    if session.get("phase") == "executing":
        raise HTTPException(status_code=409, detail="Mission is already executing. Use /annotate for post-start messages.")

    processor = IntakeAIProcessor()
    history_for_ai = [{"role": t["role"], "content": t["content"]} for t in session["history"]]

    try:
        result = await processor.process_message(req.message, session["contract"], history_for_ai)
    except Exception as exc:
        log.error("intake_ai_processing_failed", intake_id=intake_id, error=str(exc))
        raise HTTPException(status_code=503, detail=f"AI processing failed: {exc}") from exc

    turn_id = str(uuid.uuid4())
    session["history"].append({"role": "user", "content": req.message, "turn_id": turn_id, "ts": datetime.now().isoformat()})
    session["history"].append({"role": "assistant", "content": result["ai_reply"], "turn_id": turn_id + "_reply", "ts": datetime.now().isoformat()})

    async with _sessions_lock:
        session["contract"] = result["updated_contract"]
        readiness = result["readiness"]
        session["phase"] = "contract_ready" if readiness.is_ready else "discussing"

    _save_intake_session(intake_id, session)
    log.info("intake_chat_processed", intake_id=intake_id, phase=session["phase"], confidence=readiness.confidence)

    return IntakeChatResponse(
        intake_id=intake_id,
        turn_id=turn_id,
        phase=session["phase"],
        ai_reply=result["ai_reply"],
        contract=session["contract"],
        readiness=readiness,
        contract_delta=result["contract_delta"],
    )


@router.get("/api/intake/{intake_id}/contract")
async def get_intake_contract(intake_id: str) -> dict[str, Any]:
    """Return the current MissionContract and chat history without sending a message."""
    session = _intake_sessions.get(intake_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Intake session '{intake_id}' not found.")
    return {
        "intake_id": intake_id,
        "phase": session["phase"],
        "contract": session["contract"].model_dump(),
        "history": session["history"],
    }


@router.post("/api/intake/{intake_id}/start")
async def start_from_contract(intake_id: str, request: Request) -> dict[str, Any]:
    """
    Lock the MissionContract and start execution.
    Returns a new engine session_id that connects to the existing WS infrastructure.
    """
    session = _intake_sessions.get(intake_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Intake session '{intake_id}' not found.")

    contract: MissionContract = session["contract"]
    readiness = contract.readiness_assessment

    if not readiness.is_ready:
        raise HTTPException(
            status_code=400,
            detail=f"Contract not ready for execution (confidence={readiness.confidence:.2f}). "
                   f"Blocking gaps: {readiness.blocking_gaps}",
        )

    async with _sessions_lock:
        if session.get("phase") == "executing":
            raise HTTPException(status_code=409, detail="This intake session has already started execution.")
        contract.locked_at = datetime.now().isoformat()
        session["phase"] = "executing"

    rs_kwargs = contract.to_requirement_sheet_kwargs()
    requirement_sheet = RequirementSheet(**rs_kwargs)

    engine = UnifiedEngine()
    prepared = await engine.plan_request(
        prompt=requirement_sheet.to_prompt(),
        url=contract.target_url,
        goal=contract.objective,
        metadata={
            "requirements": requirement_sheet.to_metadata(),
            "contract": contract.model_dump(),
            "intake_id": intake_id,
        },
    )

    prepared.contract = contract

    broadcaster = request.app.state.broadcaster
    attach_web_hook(engine, broadcaster, prepared.session_id)
    live_sessions: set[str] = request.app.state.live_sessions
    live_sessions.add(prepared.session_id)

    running_tasks: dict[str, asyncio.Task] = request.app.state.running_tasks
    task = asyncio.create_task(
        _run_mission(engine, prepared, broadcaster),
        name=f"intake_mission:{prepared.session_id}",
    )
    running_tasks[prepared.session_id] = task
    request.app.state.last_session_id = prepared.session_id

    def _cleanup(_task: asyncio.Task, *, sid: str = prepared.session_id) -> None:
        running_tasks.pop(sid, None)
        live_sessions.discard(sid)

    task.add_done_callback(_cleanup)

    session["session_id"] = prepared.session_id
    session.setdefault("run_ids", [])
    session["run_ids"] = [*session["run_ids"], prepared.session_id]
    contract.session_id = prepared.session_id
    _save_intake_session(intake_id, session)

    log.info("intake_mission_started", intake_id=intake_id, session_id=prepared.session_id)
    return {
        "session_id": prepared.session_id,
        "intake_id": intake_id,
        "phase": "executing",
        "contract": contract.model_dump(),
        "effective_goal": contract.objective,
    }


@router.post("/api/intake/{intake_id}/annotate")
async def annotate_intake(intake_id: str, req: AnnotationRequest) -> dict[str, Any]:
    """
    Post-execution annotation. Stored in history but does NOT modify the locked contract or trigger re-execution.
    """
    session = _intake_sessions.get(intake_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Intake session '{intake_id}' not found.")

    turn_id = str(uuid.uuid4())
    session["history"].append({
        "role": "user",
        "content": req.message,
        "turn_id": turn_id,
        "annotation_type": req.annotation_type,
        "ts": datetime.now().isoformat(),
    })
    session["history"].append({
        "role": "assistant",
        "content": f"Noted [{req.annotation_type}]: {req.message}. The current mission will continue with the locked contract.",
        "turn_id": turn_id + "_ack",
        "ts": datetime.now().isoformat(),
    })
    _save_intake_session(intake_id, session)
    return {"turn_id": turn_id, "recorded": True, "annotation_type": req.annotation_type}


# ---------------------------------------------------------------------------
# Direct mission routes (legacy, bypasses intake flow)
# ---------------------------------------------------------------------------

@router.post("/api/mission/start", response_model=MissionResponse)
async def start_mission(req: MissionRequest, request: Request) -> MissionResponse:
    auto_analysis = None
    if not req.goal or not req.key_fields:
        auto_analysis = await _auto_analyse(req.url, req.goal, req.key_fields)

    requirement_sheet = _build_requirement_sheet(req, auto_analysis)
    engine = UnifiedEngine()
    prepared = await engine.plan_request(
        prompt=requirement_sheet.to_prompt(),
        url=req.url,
        goal=requirement_sheet.objective,
        metadata={
            "requirements": requirement_sheet.to_metadata(),
            "web_intake": _sanitized_web_intake(req, auto_analysis),
        },
    )

    broadcaster = request.app.state.broadcaster
    attach_web_hook(engine, broadcaster, prepared.session_id)
    live_sessions: set[str] = request.app.state.live_sessions
    live_sessions.add(prepared.session_id)

    running_tasks: dict[str, asyncio.Task] = request.app.state.running_tasks
    task = asyncio.create_task(_run_mission(engine, prepared, broadcaster), name=f"mission:{prepared.session_id}")
    running_tasks[prepared.session_id] = task
    request.app.state.last_session_id = prepared.session_id

    def _cleanup(_task: asyncio.Task, *, session_id: str = prepared.session_id) -> None:
        running_tasks.pop(session_id, None)
        live_sessions.discard(session_id)

    task.add_done_callback(_cleanup)

    return MissionResponse(
        session_id=prepared.session_id,
        site_code=str(prepared.request.metadata.get("site_code") or ""),
        site_key=str(prepared.request.metadata.get("site_key") or ""),
        status="started",
        message=f"Mission {prepared.session_id} started.",
        effective_goal=requirement_sheet.objective,
        auto_analysis=auto_analysis,
    )


@router.post("/api/mission/stop")
async def stop_mission(request: Request, payload: MissionStopRequest | None = None) -> dict[str, str]:
    running_tasks: dict[str, asyncio.Task] = request.app.state.running_tasks
    if not running_tasks:
        return {"status": "no_running_mission"}

    requested_session_id = (payload.session_id if payload else "") or str(request.app.state.last_session_id or "")
    if not requested_session_id:
        requested_session_id = list(running_tasks.keys())[-1]
    task = running_tasks.pop(requested_session_id, None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Mission '{requested_session_id}' is not running.")
    task.cancel()
    return {"status": "stopped", "session_id": requested_session_id}
