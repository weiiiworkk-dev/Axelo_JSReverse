from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from axelo.config import settings
from axelo.engine.models import PreparedRun, RequirementSheet
from axelo.engine.runtime import UnifiedEngine
from axelo.models.contracts import MissionContract

log = structlog.get_logger()

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
            datetime.fromisoformat(
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
    run_ids = [str(item) for item in (session.get("run_ids") or []) if item]
    if contract is not None:
        if hasattr(contract, "model_dump_json"):
            (d / "contract.json").write_text(
                contract.model_dump_json(indent=2), encoding="utf-8"
            )
        else:
            (d / "contract.json").write_text(
                json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    lines = "\n".join(json.dumps(turn, ensure_ascii=False) for turn in history)
    (d / "history.jsonl").write_text(lines + "\n" if lines else "", encoding="utf-8")
    if session.get("session_id"):
        (d / "session_id.txt").write_text(session["session_id"], encoding="utf-8")
    (d / "run_ids.json").write_text(json.dumps(run_ids, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mission execution helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Auto-analysis helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# RequirementSheet builder helpers
# ---------------------------------------------------------------------------

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


def _build_requirement_sheet(req: Any, auto_analysis: dict[str, Any] | None) -> RequirementSheet:
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


def _sanitized_web_intake(req: Any, auto_analysis: dict[str, Any] | None) -> dict[str, Any]:
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
