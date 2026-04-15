"""WebSocket 连接管理器：维护每个 session 的订阅连接，广播实时事件。"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
import structlog

log = structlog.get_logger()


class EventBroadcaster:
    """每个 session 可有多个 WebSocket 订阅者，广播时并发推送。"""

    def __init__(self) -> None:
        # session_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[session_id].add(ws)
        log.info("ws_client_connected", session_id=session_id, total=len(self._connections[session_id]))

    def disconnect(self, session_id: str, ws: WebSocket) -> None:
        self._connections[session_id].discard(ws)
        if not self._connections[session_id]:
            del self._connections[session_id]
        log.info("ws_client_disconnected", session_id=session_id)

    async def broadcast(self, session_id: str, payload: dict[str, Any]) -> None:
        connections = list(self._connections.get(session_id, set()))
        if not connections:
            return
        message = json.dumps(payload, ensure_ascii=False)
        results = await asyncio.gather(
            *(_safe_send(ws, message) for ws in connections),
            return_exceptions=True,
        )
        # Remove dead connections
        dead = {ws for ws, result in zip(connections, results) if isinstance(result, Exception)}
        for ws in dead:
            self.disconnect(session_id, ws)

    def active_sessions(self) -> list[str]:
        return list(self._connections.keys())


async def _safe_send(ws: WebSocket, message: str) -> None:
    await ws.send_text(message)
