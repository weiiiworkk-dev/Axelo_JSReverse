from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from axelo.config import settings
from axelo.engine.models import PreparedRun, RequirementSheet
from axelo.engine.principal import IntakeAIProcessor
from axelo.engine.runtime import UnifiedEngine
from axelo.models.contracts import MissionContract
from axelo.web.engine_hook import attach_web_hook

log = structlog.get_logger()
router = APIRouter()

# ---------------------------------------------------------------------------
# Intake session state (in-memory + filesystem persistence)
# ---------------------------------------------------------------------------

_intake_sessions: dict[str, dict[str, Any]] = {}  # intake_id → IntakeSession dict
_sessions_lock = asyncio.Lock()                    # 保护并发写入
_SESSION_TTL_SECONDS = 3600 * 6                    # 6 小时后过期清理


def _intake_session_dir(intake_id: str) -> Path:
    base = Path(settings.workspace) / "intake" / intake_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def _evict_stale_sessions() -> None:
    """清理超过 TTL 的 intake session（内存中），防止无限增长。"""
    import time as _time
    now = _time.time()
    stale = [
        sid for sid, s in _intake_sessions.items()
        if s.get("phase") not in ("executing",)
        and (now - _time.mktime(
            __import__("datetime").datetime.fromisoformat(
                s.get("created_at", "2000-01-01T00:00:00")
            ).timetuple()
        )) > _SESSION_TTL_SECONDS
    ]
    for sid in stale:
        _intake_sessions.pop(sid, None)
    if stale:
        log.info("intake_sessions_evicted", count=len(stale))


def _save_intake_session(intake_id: str, session: dict[str, Any]) -> None:
    d = _intake_session_dir(intake_id)
    contract = session.get("contract")
    history = session.get("history", [])
    if contract is not None:
        (d / "contract.json").write_text(
            contract.model_dump_json(indent=2), encoding="utf-8"
        )
    lines = "\n".join(json.dumps(turn, ensure_ascii=False) for turn in history)
    (d / "history.jsonl").write_text(lines + "\n" if lines else "", encoding="utf-8")
    if session.get("session_id"):
        (d / "session_id.txt").write_text(session["session_id"], encoding="utf-8")


# ---------------------------------------------------------------------------
# Intake Pydantic models
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
        # Lock the contract and mark phase atomically
        contract.locked_at = datetime.now().isoformat()
        session["phase"] = "executing"

    # Convert MissionContract to RequirementSheet for engine backwards compat
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

    # Attach contract to PreparedRun for field evidence population
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

    # Persist session_id linkage
    session["session_id"] = prepared.session_id
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


async def _auto_analyse(url: str, goal: str, key_fields: list[str]) -> dict[str, Any]:
    try:
        from axelo.ai.client import get_client  # type: ignore

        client = get_client()
        prompt = (
            "You are a web API reverse engineering expert.\n"
            f"Target URL: {url}\n"
            f"User goal hint: {goal or '(none)'}\n"
            f"Known fields: {', '.join(key_fields) if key_fields else '(none)'}\n\n"
            "Return strict JSON with keys: goal, key_fields, data_type, stealth_recommendation, js_required.\n"
            "Do not return markdown."
        )
        result = await client.complete(prompt, max_tokens=300)
        parsed = json.loads(result)
        if isinstance(parsed, dict):
            return parsed
    except Exception as exc:
        log.debug("web_auto_analyse_fallback", error=str(exc))
    return _heuristic_analyse(url)


def _heuristic_analyse(url: str) -> dict[str, Any]:
    url_lower = url.lower()
    if any(token in url_lower for token in ("login", "auth", "signin", "token", "oauth", "sso")):
        return {
            "goal": "Capture and reverse engineer the authentication flow and token mechanism.",
            "key_fields": ["token", "access_token", "refresh_token", "session_id", "signature", "timestamp"],
            "data_type": "auth_api",
            "stealth_recommendation": "high",
            "js_required": True,
        }
    if any(token in url_lower for token in ("search", "query", "find", "suggest", "autocomplete")):
        return {
            "goal": "Reverse engineer the search API transport and result schema.",
            "key_fields": ["query", "keyword", "filters", "sort", "page", "results", "total"],
            "data_type": "search_api",
            "stealth_recommendation": "medium",
            "js_required": True,
        }
    if any(token in url_lower for token in ("product", "item", "listing", "sku", "catalog", "shop")):
        return {
            "goal": "Collect listing data and reverse any request signing required.",
            "key_fields": ["product_id", "price", "stock", "sku", "category", "seller_id", "signature"],
            "data_type": "product_data",
            "stealth_recommendation": "medium",
            "js_required": True,
        }
    if any(token in url_lower for token in ("user", "profile", "account", "member")):
        return {
            "goal": "Recover the profile data transport and authorization requirements.",
            "key_fields": ["user_id", "uid", "token", "profile_data", "permissions"],
            "data_type": "user_data",
            "stealth_recommendation": "high",
            "js_required": False,
        }
    if any(token in url_lower for token in ("ws", "websocket", "socket", "stream", "realtime", "live")):
        return {
            "goal": "Recover the realtime transport protocol and message schema.",
            "key_fields": ["event_type", "payload", "auth_token", "channel", "message_id"],
            "data_type": "realtime",
            "stealth_recommendation": "low",
            "js_required": True,
        }
    return {
        "goal": "Reverse engineer the target API and recover trustworthy crawl artifacts.",
        "key_fields": ["api_key", "signature", "timestamp", "nonce", "token", "response_schema"],
        "data_type": "custom",
        "stealth_recommendation": "medium",
        "js_required": True,
    }


async def _run_mission(engine: UnifiedEngine, prepared: PreparedRun, broadcaster: Any) -> None:
    session_id = prepared.session_id
    try:
        await engine.execute_prepared(prepared)
    except asyncio.CancelledError:
        log.info("web_mission_cancelled", session_id=session_id)
        await broadcaster.broadcast(
            session_id,
            {
                "type": "engine_event",
                "session_id": session_id,
                "kind": "error",
                "message": "Mission cancelled by operator.",
                "agent_role": "principal",
                "state": {"mission_status": "failed"},
            },
        )
    except Exception as exc:
        log.error("web_mission_failed", session_id=session_id, error=str(exc))
        await broadcaster.broadcast(
            session_id,
            {
                "type": "engine_event",
                "session_id": session_id,
                "kind": "error",
                "message": f"Mission failed: {exc}",
                "agent_role": "principal",
                "state": {"mission_status": "failed"},
            },
        )


def _sanitized_web_intake(req: MissionRequest, auto_analysis: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "url": req.url,
        "scope": req.scope,
        "login_required": req.login_required,
        "data_type": req.data_type,
        "goal": req.goal,
        "key_fields": list(req.key_fields),
        "target_records": req.target_records,
        "sample_size": req.sample_size,
        "auth_mechanism": req.auth_mechanism,
        "stealth": req.stealth,
        "js_rendering": req.js_rendering,
        "max_pages": req.max_pages,
        "requests_per_sec": req.requests_per_sec,
        "concurrency": req.concurrency,
        "timeout_sec": req.timeout_sec,
        "retry": req.retry,
        "verify": req.verify,
        "budget_usd": req.budget_usd,
        "time_limit_min": req.time_limit_min,
        "output_format": req.output_format,
        "dedup": req.dedup,
        "session_label": req.session_label,
        "operator_credentials_provided": bool(req.username or req.password),
        "operator_username_provided": bool(req.username),
        "auto_analysis": auto_analysis or {},
    }


def _build_requirement_sheet(req: MissionRequest, auto_analysis: dict[str, Any] | None) -> RequirementSheet:
    auto_analysis = auto_analysis or {}
    objective = (req.goal or str(auto_analysis.get("goal") or "").strip() or _goal_from_data_type(req.data_type)).strip()
    key_fields = list(req.key_fields or auto_analysis.get("key_fields") or [])
    auth_notes = [
        f"Auth mechanism: {req.auth_mechanism}",
        f"Login required: {'yes' if req.login_required else 'no'}",
    ]
    if req.username or req.password:
        auth_notes.append("Operator provided credentials for interactive login assistance.")
    constraints = [
        f"Scope: {req.scope}",
        f"Stealth: {req.stealth}",
        f"JS rendering: {req.js_rendering}",
        f"Concurrency: {req.concurrency}",
        f"Req/sec: {req.requests_per_sec}",
        f"Max pages: {req.max_pages}",
        f"Timeout: {req.timeout_sec}s",
        f"Retry: {'enabled' if req.retry else 'disabled'}",
        f"Verification: {'enabled' if req.verify else 'disabled'}",
        f"Budget: ${req.budget_usd}",
        f"Time limit: {req.time_limit_min} min",
    ]
    output_expectation = [
        f"Output format: {req.output_format}",
        f"Dedup: {'enabled' if req.dedup else 'disabled'}",
    ]
    if req.session_label:
        output_expectation.append(f"Session label: {req.session_label}")
    return RequirementSheet(
        target_url=req.url,
        objective=objective,
        target_scope=req.scope,
        fields=key_fields,
        item_limit=req.target_records,
        auth_notes="; ".join(auth_notes),
        constraints="; ".join(constraints),
        output_expectation="; ".join(output_expectation),
    )


def _goal_from_data_type(data_type: str) -> str:
    mapping = {
        "auth_api": "Capture and reverse engineer the authentication flow and token mechanism.",
        "search_api": "Reverse engineer the search API transport and result schema.",
        "product_data": "Collect listing data and reverse any request signing required.",
        "user_data": "Recover the profile data transport and authorization requirements.",
        "realtime": "Recover the realtime transport protocol and message schema.",
        "custom": "Reverse engineer the target API and recover trustworthy crawl artifacts.",
    }
    return mapping.get(data_type or "custom", mapping["custom"])
