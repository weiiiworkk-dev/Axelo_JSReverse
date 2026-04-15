"""EngineHook：当引擎在同进程中运行时，将其 callback 直接接入 EventBroadcaster，实现零延迟推送。

用法示例:
    from axelo.engine.runtime import UnifiedEngine
    from axelo.web.engine_hook import attach_web_hook

    engine = UnifiedEngine()
    attach_web_hook(engine, broadcaster, session_id)
    prepared = await engine.plan_request(...)
    result = await engine.execute_prepared(prepared)
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from axelo.web.event_broadcaster import EventBroadcaster
from axelo.web.session_watcher import _build_ws_payload

log = structlog.get_logger()


def _schedule_broadcast(broadcaster: EventBroadcaster, session_id: str, payload: dict[str, Any]) -> None:
    """线程安全地将广播协程调度到当前运行的事件循环。

    引擎回调（_on_event / _on_thinking）总是从 asyncio Task 内部调用，
    因此 get_running_loop() 必定成功。使用 create_task 而非 ensure_future
    以避免 Python 3.10+ 弃用警告。
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环 —— 跳过广播（不应发生，但做防御性处理）
        log.debug("engine_hook_no_loop", session_id=session_id)
        return

    # call_soon_threadsafe 确保即使从不同线程调用也安全
    loop.call_soon_threadsafe(
        asyncio.ensure_future,
        broadcaster.broadcast(session_id, payload),
    )


def attach_web_hook(engine: Any, broadcaster: EventBroadcaster, session_id: str) -> None:
    """将 UnifiedEngine 的 event_callback 和 thinking_callback 接入广播器。

    多次调用是安全的 —— 每次都会覆盖旧 callback。
    """

    def _on_event(kind: str, message: str, payload: dict[str, Any]) -> None:
        record = {"kind": kind, "message": message, "data": payload}
        ws_payload = _build_ws_payload(session_id, record)
        _schedule_broadcast(broadcaster, session_id, ws_payload)

    def _on_thinking(thinking: str) -> None:
        ws_payload = {
            "type": "engine_event",
            "session_id": session_id,
            "kind": "thinking",
            "message": thinking,
            "state": {},
        }
        _schedule_broadcast(broadcaster, session_id, ws_payload)

    engine.set_event_callback(_on_event)
    engine.set_thinking_callback(_on_thinking)
    log.info("engine_web_hook_attached", session_id=session_id)
