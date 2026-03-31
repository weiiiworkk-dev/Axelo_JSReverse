from __future__ import annotations
import time
from abc import ABC, abstractmethod
from axelo.models.pipeline import PipelineState, StageResult
from axelo.modes.base import ModeController


class PipelineStage(ABC):
    """所有流水线阶段的基类"""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        **kwargs,
    ) -> StageResult:
        ...

    async def execute(
        self,
        state: PipelineState,
        mode: ModeController,
        **kwargs,
    ) -> StageResult:
        """带计时和错误捕获的执行封装"""
        t0 = time.monotonic()
        try:
            result = await self.run(state, mode, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            result = StageResult(
                stage_name=self.name,
                success=False,
                error=str(e),
                duration_seconds=time.monotonic() - t0,
            )
        result.duration_seconds = time.monotonic() - t0
        return result
