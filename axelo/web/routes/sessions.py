from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from axelo.config import settings
from axelo.utils.session_catalog import SessionCatalog, session_dir_for_id

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    sessions_dir = Path(settings.workspace) / "sessions"
    if not sessions_dir.exists():
        return []
    return SessionCatalog(sessions_dir).list_sessions()


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    sessions_dir = Path(settings.workspace) / "sessions"
    session_dir = _find_session_dir(sessions_dir, session_id)
    if not session_dir:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

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


@router.get("/sessions/{session_id}/events")
async def get_session_events(session_id: str, since_line: int = 0) -> dict[str, Any]:
    sessions_dir = Path(settings.workspace) / "sessions"
    session_dir = _find_session_dir(sessions_dir, session_id)
    if not session_dir:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    events_path = session_dir / "logs" / "events.jsonl"
    if not events_path.exists():
        return {"events": [], "next_line": since_line}

    lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    new_lines = lines[since_line:]
    events: list[dict[str, Any]] = []
    for line in new_lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"events": events, "next_line": since_line + len(new_lines)}


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
