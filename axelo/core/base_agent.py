from __future__ import annotations

import time
from abc import ABC, abstractmethod

import structlog

from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()


class BaseAgent(ABC):
    name: str = "base"

    async def run(self, task: SubTask) -> AgentResult:
        """Public entry: timing, status marking, exception capture."""
        task.mark_running()
        logger = log.bind(agent=self.name, task_id=task.id, attempt=task.attempt)
        logger.info("agent_started", objective=task.objective)
        t0 = time.monotonic()
        try:
            result = await self.execute(task)
            result.duration_ms = round((time.monotonic() - t0) * 1000, 1)
            task.mark_complete(result)
            logger.info("agent_complete", status=result.status, duration_ms=result.duration_ms)
            return result
        except Exception as exc:
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            err = str(exc)
            task.mark_failed(err)
            logger.error("agent_failed", error=err, duration_ms=duration_ms)
            return AgentResult(
                agent=self.name,
                status=ResultStatus.FAILURE,
                error=err,
                duration_ms=duration_ms,
            )

    @abstractmethod
    async def execute(self, task: SubTask) -> AgentResult:
        """Subclasses implement domain logic here."""
        ...
