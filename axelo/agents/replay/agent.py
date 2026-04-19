from __future__ import annotations

from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()

_MIN_SUCCESS_RATE = 0.8


class ReplayAgent(BaseAgent):
    name = "replay"

    async def execute(self, task: SubTask) -> AgentResult:
        code = task.meta.get("code", "")
        target_url = task.meta.get("target_url", "")
        log.info("replay_start", url=target_url)

        stats = await self._replay_requests(code, target_url)
        success_rate = stats.get("success_rate", 0.0)
        log.info("replay_done", success_rate=success_rate)

        if success_rate >= _MIN_SUCCESS_RATE:
            return AgentResult(agent=self.name, status=ResultStatus.SUCCESS, data=stats)
        return AgentResult(
            agent=self.name,
            status=ResultStatus.FAILURE,
            data=stats,
            error=f"success_rate_too_low: {success_rate:.0%}",
        )

    async def _replay_requests(self, code: str, url: str) -> dict[str, Any]:
        from axelo.agents.replay.tools.replayer import Replayer
        replayer = Replayer()
        return await replayer.replay(code=code, target_url=url, n=10)
