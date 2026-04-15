"""SessionWatcher：监听磁盘上 events.jsonl 文件的增量写入，推送给 WebSocket 客户端。

当引擎在同一进程时，engine_hook 会直接调用 broadcaster.broadcast()，延迟为 0。
当引擎在另一进程时，此 watcher 以 tail 模式轮询文件，延迟约 0.5s。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from axelo.web.event_broadcaster import EventBroadcaster

log = structlog.get_logger()

_POLL_INTERVAL = 0.5  # 秒


class SessionWatcher:
    """为指定 session 启动一个 asyncio 后台任务，持续 tail events.jsonl 并广播。"""

    def __init__(self, broadcaster: EventBroadcaster) -> None:
        self._broadcaster = broadcaster
        self._tasks: dict[str, asyncio.Task] = {}

    def watch(self, session_id: str, session_dir: Path) -> None:
        """启动后台 tail 任务（幂等，已在跑的不重复启动）。"""
        if session_id in self._tasks and not self._tasks[session_id].done():
            return
        task = asyncio.create_task(
            self._tail_loop(session_id, session_dir / "logs" / "events.jsonl"),
            name=f"watcher:{session_id}",
        )
        self._tasks[session_id] = task
        log.info("session_watcher_started", session_id=session_id)

    def stop(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    async def _tail_loop(self, session_id: str, events_path: Path) -> None:
        offset = 0
        while True:
            try:
                if events_path.exists():
                    text = events_path.read_text(encoding="utf-8", errors="ignore")
                    lines = text.splitlines()
                    new_lines = lines[offset:]
                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        payload = _build_ws_payload(session_id, record)
                        await self._broadcaster.broadcast(session_id, payload)
                    offset = len(lines)
            except Exception as exc:
                log.warning("session_watcher_error", session_id=session_id, error=str(exc))
            await asyncio.sleep(_POLL_INTERVAL)


def _build_ws_payload(session_id: str, record: dict[str, Any]) -> dict[str, Any]:
    data = record.get("data") or {}
    return {
        "type": "engine_event",
        "session_id": session_id,
        "kind": record.get("kind", "unknown"),
        "message": record.get("message", ""),
        "step": data.get("step"),
        "agent_role": _infer_agent_role(data.get("objective", "")),
        "objective": data.get("objective"),
        "published_at": record.get("published_at"),
        "state": {
            "mission_status": data.get("mission_status"),
            "mission_outcome": data.get("mission_outcome"),
            "evidence_count": data.get("evidence_count", 0),
            "hypothesis_count": data.get("hypothesis_count", 0),
            "coverage": data.get("coverage", {}),
            "trust_score": data.get("trust_score", 0.0),
            "execution_trust_score": data.get("execution_trust_score", 0.0),
            "mechanism_trust_score": data.get("mechanism_trust_score", 0.0),
            "current_focus": data.get("current_focus", ""),
            "current_uncertainty": data.get("current_uncertainty", ""),
            "dominant_hypothesis": data.get("dominant_hypothesis"),
            "mechanism_blockers": data.get("mechanism_blockers", []),
            "next_action_hint": data.get("next_action_hint"),
            "evidence_delta": data.get("evidence_delta"),
        },
    }


_OBJECTIVE_TO_ROLE: dict[str, str] = {
    "discover_surface": "recon-agent",
    "recover_transport": "transport-agent",
    "recover_static_mechanism": "reverse-agent",
    "recover_runtime_mechanism": "runtime-agent",
    "recover_response_schema": "schema-agent",
    "build_artifacts": "builder-agent",
    "verify_execution": "verifier-agent",
    "challenge_findings": "critic-agent",
    "consult_memory": "memory-agent",
}


def _infer_agent_role(objective: str) -> str:
    return _OBJECTIVE_TO_ROLE.get(objective, "principal")
