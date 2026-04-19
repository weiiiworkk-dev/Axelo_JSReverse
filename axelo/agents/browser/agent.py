from __future__ import annotations

import re
from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class BrowserAgent(BaseAgent):
    name = "browser"

    async def execute(self, task: SubTask) -> AgentResult:
        url = self._extract_url(task.objective)
        log.info("browser_start", url=url)
        data = await self._capture_bundles(url)
        return AgentResult(
            agent=self.name,
            status=ResultStatus.SUCCESS,
            data=data,
        )

    async def _capture_bundles(self, url: str) -> dict[str, Any]:
        from axelo.agents.browser.tools.driver import BrowserDriver
        from axelo.config import settings

        driver = BrowserDriver(
            browser=settings.browser,
            headless=settings.headless,
        )
        async with driver as d:
            bundles, trace = await d.capture(url)
            return {
                "url": url,
                "bundle_count": len(bundles),
                "bundles": bundles,
                "network_trace": trace,
            }

    @staticmethod
    def _extract_url(objective: str) -> str:
        m = re.search(r"https?://\S+", objective)
        return m.group() if m else objective.strip()
