"""WebSocket routes for live run events."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from axelo.config import settings
from axelo.web.event_broadcaster import EventBroadcaster
from axelo.web.session_watcher import SessionWatcher, _build_ws_payload

log = structlog.get_logger()

router = APIRouter()

_broadcaster: EventBroadcaster | None = None
_watcher: SessionWatcher | None = None


def init(broadcaster: EventBroadcaster, watcher: SessionWatcher) -> None:
    global _broadcaster, _watcher
    _broadcaster = broadcaster
    _watcher = watcher


@router.websocket("/ws/sessions/{session_id}/stream")
async def session_stream(ws: WebSocket, session_id: str) -> None:
    await _stream_run(ws, session_id)


@router.websocket("/ws/runs/{run_id}")
async def run_stream(ws: WebSocket, run_id: str) -> None:
    await _stream_run(ws, run_id)


async def _stream_run(ws: WebSocket, run_id: str) -> None:
    assert _broadcaster and _watcher, "WebSocket router not initialized"

    sessions_dir = Path(settings.workspace) / "sessions"
    session_dir = _find_session_dir(sessions_dir, run_id)
    live_sessions = getattr(ws.app.state, "live_sessions", set())
    if session_dir and run_id not in live_sessions:
        _watcher.watch(run_id, session_dir)

    await _broadcaster.connect(run_id, ws)
    try:
        if session_dir:
            events_path = session_dir / "logs" / "events.jsonl"
            if events_path.exists():
                cursor = int(ws.query_params.get("cursor", "0") or "0")
                lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                start = max(cursor, max(len(lines) - 50, 0))
                for index, line in enumerate(lines[start:], start=start + 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        payload = _build_ws_payload(run_id, record, seq=int(record.get("seq") or index))
                        await ws.send_json(payload)
                    except Exception:
                        log.debug("ws_backfill_event_ignored", run_id=run_id)

        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _broadcaster.disconnect(run_id, ws)


def _find_session_dir(sessions_dir: Path, session_id: str) -> Path | None:
    if not sessions_dir.exists():
        return None
    for site_dir in sessions_dir.iterdir():
        if not site_dir.is_dir():
            continue
        candidate = site_dir / session_id
        if candidate.is_dir():
            return candidate
    return None
