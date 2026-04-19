from __future__ import annotations

from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class VerificationAgent(BaseAgent):
    name = "verification"

    async def execute(self, task: SubTask) -> AgentResult:
        code: str = task.meta.get("code", "")
        log.info("verification_start", code_lines=len(code.splitlines()))
        vresult = await self._run_verification(code)

        if vresult.get("passed"):
            return AgentResult(
                agent=self.name,
                status=ResultStatus.SUCCESS,
                data=vresult,
            )
        return AgentResult(
            agent=self.name,
            status=ResultStatus.FAILURE,
            data=vresult,
            error=vresult.get("error", "verification_failed"),
        )

    async def _run_verification(self, code: str) -> dict[str, Any]:
        from axelo.agents.verification.tools.verify_tool import VerifyTool
        tool = VerifyTool()
        return await tool.verify(code)
