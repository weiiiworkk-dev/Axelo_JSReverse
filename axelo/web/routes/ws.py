"""WebSocket 路由：客户端订阅 session 事件流。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from axelo.config import settings
from axelo.web.event_broadcaster import EventBroadcaster
from axelo.web.session_watcher import SessionWatcher

log = structlog.get_logger()

router = APIRouter()

# 单例：由 server.py 创建并注入
_broadcaster: EventBroadcaster | None = None
_watcher: SessionWatcher | None = None


def init(broadcaster: EventBroadcaster, watcher: SessionWatcher) -> None:
    global _broadcaster, _watcher
    _broadcaster = broadcaster
    _watcher = watcher


@router.websocket("/ws/sessions/{session_id}/stream")
async def session_stream(ws: WebSocket, session_id: str) -> None:
    """客户端通过此 WS 接收实时引擎事件。"""
    assert _broadcaster and _watcher, "WebSocket router not initialized"

    # 启动磁盘 watcher（若引擎不在同进程时作为备用推送源）
    sessions_dir = Path(settings.workspace) / "sessions"
    session_dir = _find_session_dir(sessions_dir, session_id)
    live_sessions = getattr(ws.app.state, "live_sessions", set())
    if session_dir and session_id not in live_sessions:
        _watcher.watch(session_id, session_dir)

    await _broadcaster.connect(session_id, ws)
    try:
        # 推送快照：把历史事件从头发一遍（最多最近 50 条）
        if session_dir:
            events_path = session_dir / "logs" / "events.jsonl"
            if events_path.exists():
                from axelo.web.session_watcher import _build_ws_payload
                import json
                lines = events_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines[-50:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        payload = _build_ws_payload(session_id, record)
                        await ws.send_json(payload)
                    except Exception:
                        pass

        # 保持连接，直到客户端断开
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _broadcaster.disconnect(session_id, ws)


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
