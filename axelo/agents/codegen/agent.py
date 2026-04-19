from __future__ import annotations

from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class CodegenAgent(BaseAgent):
    name = "codegen"

    async def execute(self, task: SubTask) -> AgentResult:
        candidates = task.meta.get("candidates", [])
        crypto = task.meta.get("crypto_primitives", [])
        log.info("codegen_start", candidate_count=len(candidates), crypto=crypto)

        code = await self._generate_code(candidates, crypto, task.objective)
        return AgentResult(
            agent=self.name,
            status=ResultStatus.SUCCESS,
            data={"code": code, "candidates_used": candidates},
        )

    async def _generate_code(
        self, candidates: list[str], crypto: list[str], objective: str
    ) -> str:
        from axelo.agents.codegen.tools.codegen_tool import CodegenTool
        tool = CodegenTool()
        return await tool.generate(
            candidates=candidates,
            crypto_primitives=crypto,
            objective=objective,
        )
