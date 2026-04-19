from __future__ import annotations

from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class AnalysisAgent(BaseAgent):
    name = "analysis"

    async def execute(self, task: SubTask) -> AgentResult:
        bundles: list[str] = task.meta.get("bundles", [])
        log.info("analysis_start", bundle_count=len(bundles))

        static_result = await self._run_static(bundles)
        dynamic_result = await self._run_dynamic(bundles)

        data = {
            "candidates": static_result.get("candidates", []),
            "call_graph": static_result.get("call_graph", {}),
            "traces": dynamic_result.get("traces", []),
            "crypto_primitives": static_result.get("crypto_primitives", []),
        }
        return AgentResult(agent=self.name, status=ResultStatus.SUCCESS, data=data)

    async def _run_static(self, bundles: list[str]) -> dict[str, Any]:
        from axelo.agents.analysis.tools.static_tool import StaticAnalysisTool
        tool = StaticAnalysisTool()
        return await tool.analyze(bundles)

    async def _run_dynamic(self, bundles: list[str]) -> dict[str, Any]:
        from axelo.agents.analysis.tools.dynamic_analyzer import DynamicAnalyzerTool
        tool = DynamicAnalyzerTool()
        return await tool.analyze(bundles)
