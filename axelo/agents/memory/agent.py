from __future__ import annotations

from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class MemoryAgent(BaseAgent):
    name = "memory"

    async def execute(self, task: SubTask) -> AgentResult:
        domain = task.meta.get("domain", "")
        code = task.meta.get("code", "")
        antibot = task.meta.get("antibot", "unknown")
        log.info("memory_write", domain=domain, antibot=antibot)

        write_result = await self._write_pattern(domain, code, antibot)
        return AgentResult(agent=self.name, status=ResultStatus.SUCCESS, data=write_result)

    async def _write_pattern(self, domain: str, code: str, antibot: str) -> dict[str, Any]:
        from axelo.agents.memory.tools.writer import MemoryWriter
        writer = MemoryWriter()
        return await writer.write(domain=domain, code=code, antibot_system=antibot)
