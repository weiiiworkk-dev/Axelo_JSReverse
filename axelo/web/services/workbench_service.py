from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from axelo.config import settings
from axelo.web.contracts import (
    AgentStateView,
    ArtifactRef,
    ChatThreadItem,
    CheckpointRecord,
    PlanStepView,
    RunEvent,
    RunView,
    SessionSummary,
    SessionView,
)
from axelo.web.services.intake_service import _intake_sessions


OBJECTIVE_TITLES: dict[str, str] = {
    "discover_surface": "Inspect target surface",
    "recover_transport": "Recover transport path",
    "recover_static_mechanism": "Analyze static mechanism",
    "recover_runtime_mechanism": "Inspect runtime mechanism",
    "recover_response_schema": "Map response schema",
    "build_artifacts": "Build crawler artifacts",
    "verify_execution": "Verify execution",
    "challenge_findings": "Review blockers",
    "consult_memory": "Consult memory",
}

OBJECTIVE_PHASE: dict[str, str] = {
    "discover_surface": "planning",
    "recover_transport": "running",
    "recover_static_mechanism": "running",
    "recover_runtime_mechanism": "running",
    "recover_response_schema": "running",
    "build_artifacts": "running",
    "verify_execution": "running",
    "challenge_findings": "blocked",
    "consult_memory": "planning",
}


def intake_root() -> Path:
    root = Path(settings.workspace) / "intake"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_events_path(run_id: str) -> Path | None:
    session_dir = find_run_session_dir(run_id)
    if session_dir is None:
        return None
    return session_dir / "logs" / "events.jsonl"


def find_run_session_dir(run_id: str) -> Path | None:
    sessions_root = Path(settings.workspace) / "sessions"
    if not sessions_root.exists():
        return None
    for site_dir in sessions_root.iterdir():
        if not site_dir.is_dir():
            continue
        candidate = site_dir / run_id
        if candidate.is_dir():
            return candidate
    return None


def load_intake_session(session_id: str) -> dict[str, Any] | None:
    in_memory = _intake_sessions.get(session_id)
    if in_memory is not None:
        session = dict(in_memory)
        session.setdefault("run_ids", _load_run_ids(session_id))
        return session

    base = intake_root() / session_id
    if not base.exists():
        return None

    contract = _read_json(base / "contract.json") or {}
    history_lines = _read_jsonl(base / "history.jsonl")
    run_ids = _load_run_ids(session_id)
    created_at = str(contract.get("created_at") or datetime.now().isoformat())
    session_id_from_file = (base / "session_id.txt").read_text(encoding="utf-8").strip() if (base / "session_id.txt").exists() else ""
    phase = "executing" if session_id_from_file else "welcome"
    if run_ids:
        phase = "executing"
    return {
        "intake_id": session_id,
        "contract": contract,
        "history": history_lines,
        "phase": phase,
        "session_id": session_id_from_file,
        "run_ids": run_ids,
        "created_at": created_at,
    }


def save_run_ids(session_id: str, run_ids: list[str]) -> None:
    base = intake_root() / session_id
    base.mkdir(parents=True, exist_ok=True)
    (base / "run_ids.json").write_text(json.dumps(run_ids, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_run_ids(session_id: str) -> list[str]:
    path = intake_root() / session_id / "run_ids.json"
    payload = _read_json(path)
    if isinstance(payload, list):
        return [str(item) for item in payload if item]
    legacy = intake_root() / session_id / "session_id.txt"
    if legacy.exists():
        run_id = legacy.read_text(encoding="utf-8").strip()
        return [run_id] if run_id else []
    return []


def list_workbench_sessions() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    if intake_root().exists():
        for base in sorted(intake_root().iterdir(), key=lambda p: p.name, reverse=True):
            if not base.is_dir():
                continue
            session = load_intake_session(base.name)
            if session is None:
                continue
            summary = build_session_summary(session)
            records.append(summary.model_dump(mode="json"))
            seen.add(summary.session_id)

    sessions_root = Path(settings.workspace) / "sessions"
    if sessions_root.exists():
        for site_dir in sorted(sessions_root.iterdir(), key=lambda p: p.name, reverse=True):
            if not site_dir.is_dir():
                continue
            for run_dir in sorted(site_dir.iterdir(), key=lambda p: p.name, reverse=True):
                if not run_dir.is_dir():
                    continue
                run_id = run_dir.name
                if run_id in seen:
                    continue
                request_payload = _read_json(run_dir / "session_request.json") or {}
                mission_report = _read_json(run_dir / "artifacts" / "final" / "mission_report.json") or {}
                records.append(
                    SessionSummary(
                        session_id=run_id,
                        title=str(request_payload.get("goal") or request_payload.get("url") or run_id),
                        created_at=str(request_payload.get("created_at") or datetime.now().isoformat()),
                        updated_at=str(mission_report.get("updated_at") or datetime.now().isoformat()),
                        status=str(mission_report.get("mission_status") or "completed"),
                        site_key=str((request_payload.get("metadata") or {}).get("site_key") or ""),
                        site_code=str(site_dir.name),
                        url=str(request_payload.get("url") or ""),
                        latest_run_id=run_id,
                        latest_run_status=str(mission_report.get("mission_status") or "completed"),
                        is_legacy=True,
                    ).model_dump(mode="json")
                )
    return records


def build_session_summary(session: dict[str, Any]) -> SessionSummary:
    contract = session.get("contract") or {}
    run_ids = list(session.get("run_ids") or [])
    latest_run_id = run_ids[-1] if run_ids else ""
    latest_run = build_run_view(latest_run_id, session_id=str(session.get("intake_id") or "")) if latest_run_id else None
    title = (
        _contract_value(contract, "objective")
        or _contract_value(contract, "target_url")
        or f"Session {session.get('intake_id', '')[:8]}"
    )
    history = session.get("history") or []
    updated_at = history[-1].get("ts") if history else session.get("created_at") or datetime.now().isoformat()
    return SessionSummary(
        session_id=str(session.get("intake_id") or ""),
        title=title,
        created_at=str(session.get("created_at") or datetime.now().isoformat()),
        updated_at=str(updated_at),
        status=str(session.get("phase") or "idle"),
        site_key=str(_contract_value(contract, "target_url") or ""),
        latest_run_id=latest_run_id,
        latest_run_status=latest_run.status if latest_run else "idle",
        is_legacy=False,
    )


def build_session_view(session_id: str) -> SessionView | None:
    session = load_intake_session(session_id)
    if session is None:
        return None

    contract = session.get("contract") or {}
    history = session.get("history") or []
    run_ids = list(session.get("run_ids") or [])
    thread_items = project_history_to_thread(session_id, history)
    for run_id in run_ids:
        run_events = load_run_events(run_id, session_id=session_id)
        thread_items.extend(project_run_events_to_thread(run_events))

    title = (
        _contract_value(contract, "objective")
        or _contract_value(contract, "target_url")
        or f"Session {session_id[:8]}"
    )
    readiness = _contract_value(contract, "readiness_assessment", {})
    ready_to_run = False
    if isinstance(readiness, dict):
        ready_to_run = bool(readiness.get("is_ready"))
    else:
        ready_to_run = bool(getattr(readiness, "is_ready", False))
    return SessionView(
        session_id=session_id,
        title=title,
        created_at=str(session.get("created_at") or datetime.now().isoformat()),
        updated_at=thread_items[-1].created_at if thread_items else str(session.get("created_at") or datetime.now().isoformat()),
        status=str(session.get("phase") or "idle"),
        intake_id=session_id,
        current_run_id=run_ids[-1] if run_ids else "",
        run_ids=run_ids,
        ready_to_run=ready_to_run,
        thread_items=thread_items,
    )


def build_run_view(run_id: str, *, session_id: str = "") -> RunView:
    session_dir = find_run_session_dir(run_id)
    if session_dir is None:
        return RunView(run_id=run_id, session_id=session_id)

    mission_report = _read_json(session_dir / "artifacts" / "final" / "mission_report.json") or {}
    run_events = load_run_events(run_id, session_id=session_id)
    artifacts = build_artifact_refs(run_id)
    checkpoints = load_checkpoints(run_id)

    plan_steps: dict[str, PlanStepView] = {}
    agents: dict[str, AgentStateView] = {}
    recent_event = ""
    last_seq = 0

    for event in run_events:
        last_seq = max(last_seq, event.seq)
        if event.payload.get("message"):
            recent_event = str(event.payload.get("message"))
        objective = str(event.payload.get("objective") or "")
        agent_id = str(event.actor_id or "")
        if objective:
            step = plan_steps.get(objective) or PlanStepView(
                step_id=objective,
                title=OBJECTIVE_TITLES.get(objective, objective.replace("_", " ").title()),
                agent_id=agent_id,
            )
            step.status = _step_status_from_event(event.kind, event.payload)
            step.note = str(event.payload.get("message") or step.note)
            step.updated_at = event.ts
            step.agent_id = agent_id or step.agent_id
            plan_steps[objective] = step
        if agent_id and agent_id != "router":
            agent = agents.get(agent_id) or AgentStateView(
                agent_id=agent_id,
                label=agent_id,
            )
            agent.status = _agent_status_from_event(event.kind, event.payload)
            agent.current_task = str(event.payload.get("objective_label") or event.payload.get("message") or agent.current_task)
            agent.last_update = event.ts
            agents[agent_id] = agent

    raw_status = str(mission_report.get("mission_status") or "running")
    phase = str(mission_report.get("mission_status") or "running")
    return RunView(
        run_id=run_id,
        session_id=session_id,
        status=_normalize_run_status(raw_status),
        phase=_normalize_run_phase(phase),
        objective_text=str(mission_report.get("objective") or mission_report.get("target_url") or run_id),
        phase_label=_human_phase_label(phase),
        plan_steps=list(plan_steps.values()),
        agents=list(agents.values()),
        checkpoints=checkpoints,
        artifacts=artifacts,
        recent_event=recent_event,
        connection_status="offline",
        last_seq=last_seq,
    )


def build_artifact_refs(run_id: str) -> list[ArtifactRef]:
    session_dir = find_run_session_dir(run_id)
    if session_dir is None:
        return []
    artifact_index = _read_json(session_dir / "artifacts" / "final" / "artifact_index.json") or {}
    refs: list[ArtifactRef] = []
    for item in artifact_index.get("artifacts", []) if isinstance(artifact_index, dict) else []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        refs.append(
            ArtifactRef(
                artifact_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{path}")),
                run_id=run_id,
                title=str(item.get("name") or Path(path).name or "Artifact"),
                artifact_type=str(item.get("category") or "artifact"),
                uri=path,
                summary=str(item.get("description") or ""),
            )
        )
    return refs


def load_checkpoints(run_id: str) -> list[CheckpointRecord]:
    path = intake_root() / "_checkpoints" / f"{run_id}.json"
    payload = _read_json(path)
    if not isinstance(payload, list):
        return []
    records: list[CheckpointRecord] = []
    for item in payload:
        if isinstance(item, dict):
            records.append(CheckpointRecord.model_validate(item))
    return records


def save_checkpoint_resolution(run_id: str, checkpoint_id: str, approved: bool) -> CheckpointRecord:
    records = load_checkpoints(run_id)
    found: CheckpointRecord | None = None
    for record in records:
        if record.checkpoint_id == checkpoint_id:
            record.status = "approved" if approved else "rejected"
            record.resolved_at = datetime.now().isoformat()
            record.resolution = "approved" if approved else "rejected"
            found = record
            break
    if found is None:
        found = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            question="Manual checkpoint resolution",
            status="approved" if approved else "rejected",
            resolved_at=datetime.now().isoformat(),
            resolution="approved" if approved else "rejected",
        )
        records.append(found)
    base = intake_root() / "_checkpoints"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{run_id}.json").write_text(
        json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return found


def load_run_events(run_id: str, *, session_id: str = "", cursor: int = 0) -> list[RunEvent]:
    path = run_events_path(run_id)
    if path is None or not path.exists():
        return []
    records = _read_jsonl(path)
    events = [adapt_legacy_record(run_id, session_id, record, seq=index + 1) for index, record in enumerate(records)]
    return [event for event in events if event.seq > cursor]


def adapt_legacy_record(run_id: str, session_id: str, record: dict[str, Any], *, seq: int) -> RunEvent:
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    legacy_kind = str(record.get("kind") or "info")
    objective = str(data.get("objective") or "")
    actor_id = _infer_agent_id(objective)
    kind = "router.message"
    actor_type: str = "router"
    payload: dict[str, Any] = {
        "message": str(record.get("message") or ""),
        "objective": objective,
        "objective_label": OBJECTIVE_TITLES.get(objective, objective.replace("_", " ").title() if objective else ""),
        "legacy_kind": legacy_kind,
        **data,
    }

    if legacy_kind == "dispatch":
        kind = "agent.activity"
        actor_type = "agent"
        payload["status"] = "running"
    elif legacy_kind == "complete":
        kind = "run.completed" if data.get("artifact_index") or data.get("mission_status") in {"success", "failed", "partial"} else "agent.activity"
        actor_type = "system" if kind == "run.completed" else "agent"
        payload["status"] = "completed"
    elif legacy_kind == "error":
        kind = "run.failed" if data.get("mission_status") == "failed" else "agent.activity"
        actor_type = "system" if kind == "run.failed" else "agent"
        payload["status"] = "failed"
    elif legacy_kind == "risk":
        kind = "agent.activity"
        actor_type = "agent"
        payload["status"] = "blocked"
    elif legacy_kind in {"verdict", "field_evidence"}:
        kind = "deliverable.created"
        actor_type = "system"
    elif legacy_kind == "mission":
        kind = "run.created"
        actor_type = "system"
    elif legacy_kind == "thinking":
        kind = "agent.activity"
        actor_type = "agent"
        payload["status"] = "running"
        payload["transient"] = True
    elif legacy_kind == "reconciliation":
        kind = "router.message"
        actor_type = "router"

    return RunEvent(
        event_id=str(record.get("event_id") or f"{run_id}:{seq}"),
        session_id=session_id,
        run_id=run_id,
        seq=int(record.get("seq") or seq),
        ts=str(record.get("published_at") or record.get("ts") or datetime.now().isoformat()),
        kind=kind,
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_id=actor_id if actor_type == "agent" else ("router" if actor_type == "router" else "system"),
        phase=_normalize_run_phase(str(data.get("mission_status") or OBJECTIVE_PHASE.get(objective, "running"))),
        payload=payload,
    )


def project_history_to_thread(session_id: str, history: list[dict[str, Any]]) -> list[ChatThreadItem]:
    items: list[ChatThreadItem] = []
    for turn in history:
        role = str(turn.get("role") or "assistant")
        kind = "user_message" if role == "user" else "router_message"
        actor_type = "user" if role == "user" else "router"
        actor_id = "user" if role == "user" else "router"
        items.append(
            ChatThreadItem(
                item_id=str(turn.get("turn_id") or uuid.uuid4()),
                session_id=session_id,
                kind=kind,  # type: ignore[arg-type]
                created_at=str(turn.get("ts") or datetime.now().isoformat()),
                actor_type=actor_type,  # type: ignore[arg-type]
                actor_id=actor_id,
                content=str(turn.get("content") or ""),
                meta={"annotation_type": turn.get("annotation_type", "")},
            )
        )
    return items


def project_run_events_to_thread(events: list[RunEvent]) -> list[ChatThreadItem]:
    blocks: dict[tuple[str, str], ChatThreadItem] = {}
    ordered: list[ChatThreadItem] = []
    for event in events:
        if event.kind == "run.created":
            ordered.append(
                ChatThreadItem(
                    item_id=f"notice:{event.event_id}",
                    session_id=event.session_id,
                    run_id=event.run_id,
                    kind="system_notice",
                    created_at=event.ts,
                    actor_type="system",
                    actor_id="system",
                    title="Run started",
                    content=str(event.payload.get("message") or "Router started a new run."),
                    meta={"phase": event.phase},
                )
            )
            continue

        if event.kind == "router.message":
            ordered.append(
                ChatThreadItem(
                    item_id=f"router:{event.event_id}",
                    session_id=event.session_id,
                    run_id=event.run_id,
                    kind="router_message",
                    created_at=event.ts,
                    actor_type="router",
                    actor_id="router",
                    content=str(event.payload.get("message") or ""),
                    meta={"phase": event.phase},
                )
            )
            continue

        if event.kind == "deliverable.created":
            ordered.append(
                ChatThreadItem(
                    item_id=f"deliverable:{event.event_id}",
                    session_id=event.session_id,
                    run_id=event.run_id,
                    kind="deliverable_block",
                    created_at=event.ts,
                    actor_type="system",
                    actor_id="system",
                    title="Deliverable",
                    content=str(event.payload.get("message") or ""),
                    status=str(event.payload.get("status") or ""),
                    meta={"kind": event.kind, "phase": event.phase},
                )
            )
            continue

        if event.kind in {"run.completed", "run.failed"}:
            ordered.append(
                ChatThreadItem(
                    item_id=f"run:{event.event_id}",
                    session_id=event.session_id,
                    run_id=event.run_id,
                    kind="system_notice",
                    created_at=event.ts,
                    actor_type="system",
                    actor_id="system",
                    title="Run update",
                    content=str(event.payload.get("message") or ""),
                    status="failed" if event.kind == "run.failed" else "completed",
                    meta={"phase": event.phase},
                )
            )
            continue

        if event.kind != "agent.activity" or event.payload.get("transient"):
            continue

        key = (event.run_id, event.actor_id)
        block = blocks.get(key)
        recent_actions = []
        if block is not None:
            recent_actions = list(block.meta.get("recent_actions") or [])
        recent_actions.append(str(event.payload.get("message") or ""))
        recent_actions = [item for item in recent_actions if item][-3:]
        content = "\n".join(recent_actions)
        title = str(event.payload.get("objective_label") or event.actor_id)

        if block is None or block.status in {"failed", "completed"}:
            block = ChatThreadItem(
                item_id=f"activity:{event.event_id}",
                session_id=event.session_id,
                run_id=event.run_id,
                kind="agent_activity_block",
                created_at=event.ts,
                actor_type="agent",
                actor_id=event.actor_id,
                title=title,
                content=content,
                status=str(event.payload.get("status") or "running"),
                meta={
                    "objective": event.payload.get("objective", ""),
                    "recent_actions": recent_actions,
                },
            )
            blocks[key] = block
            ordered.append(block)
        else:
            block.created_at = event.ts
            block.title = title
            block.content = content
            block.status = str(event.payload.get("status") or block.status)
            block.meta["objective"] = event.payload.get("objective", "")
            block.meta["recent_actions"] = recent_actions
    return ordered


def _normalize_run_status(status: str) -> str:
    if status in {"success", "completed"}:
        return "completed"
    if status in {"partial"}:
        return "blocked"
    if status in {"failed", "error"}:
        return "failed"
    if status in {"active", "running", "executing"}:
        return "running"
    return "idle"


def _normalize_run_phase(phase: str) -> str:
    if phase in {"success", "completed"}:
        return "completed"
    if phase in {"failed", "error"}:
        return "failed"
    if phase in {"partial", "blocked", "paused"}:
        return "blocked"
    if phase in {"planning", "intake"}:
        return phase
    return "running"


def _human_phase_label(phase: str) -> str:
    mapping = {
        "intake": "Intake",
        "planning": "Planning",
        "running": "Running",
        "blocked": "Waiting",
        "completed": "Completed",
        "failed": "Failed",
    }
    return mapping.get(_normalize_run_phase(phase), "Running")


def _step_status_from_event(kind: str, payload: dict[str, Any]) -> str:
    if kind == "run.failed":
        return "failed"
    status = str(payload.get("status") or "")
    if status in {"completed", "failed", "blocked", "running"}:
        return status
    return "pending"


def _agent_status_from_event(kind: str, payload: dict[str, Any]) -> str:
    if kind == "run.failed":
        return "failed"
    status = str(payload.get("status") or "")
    if status in {"completed", "failed", "blocked", "running"}:
        return status
    return "idle"


def _infer_agent_id(objective: str) -> str:
    mapping = {
        "discover_surface": "browser-agent",
        "recover_transport": "network-agent",
        "recover_static_mechanism": "reverse-agent",
        "recover_runtime_mechanism": "runtime-agent",
        "recover_response_schema": "extraction-agent",
        "build_artifacts": "codegen-agent",
        "verify_execution": "verification-agent",
        "challenge_findings": "router",
        "consult_memory": "memory-agent",
    }
    return mapping.get(objective, "router")


def _read_json(path: Path) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            lines.append(payload)
    return lines


def _contract_value(contract: Any, key: str, default: Any = "") -> Any:
    if isinstance(contract, dict):
        return contract.get(key, default)
    return getattr(contract, key, default)


async def run_router_session(target_url: str, objective: str) -> dict[str, Any]:
    """Start a Router AI session. Returns session_id and final status."""
    from axelo.core.router.router import Router
    from axelo.core.router.default_registry import build_default_registry

    router = Router(
        registry=build_default_registry(),
        artifacts_root=settings.workspace.parent / "artifacts",
    )
    return await router.run(target_url=target_url, objective=objective)
