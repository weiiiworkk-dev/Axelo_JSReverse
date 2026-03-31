from __future__ import annotations
from datetime import datetime
from pathlib import Path
import structlog

from axelo.models.pipeline import PipelineState, StageRecord, StageStatus
from axelo.modes.base import ModeController
from axelo.storage.session_store import SessionStore
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()


class PipelineOrchestrator:
    """
    流水线协调器：按顺序执行各 Stage，管理状态持久化，
    在决策点调用 ModeController.gate()。
    支持从任意已完成阶段断点续跑。
    """

    def __init__(
        self,
        stages: list[PipelineStage],
        store: SessionStore,
    ) -> None:
        self._stages = stages
        self._store = store

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        **stage_kwargs,
    ) -> PipelineState:
        # 初始化阶段记录
        if not state.stages:
            state.stages = [
                StageRecord(stage_name=s.name) for s in self._stages
            ]

        for i, stage in enumerate(self._stages):
            record = state.stages[i] if i < len(state.stages) else None
            if record and record.status == StageStatus.COMPLETED:
                log.info("stage_skip_completed", stage=stage.name)
                continue
            if record and record.status == StageStatus.SKIPPED:
                log.info("stage_skip_manual", stage=stage.name)
                continue

            # 更新状态
            state.current_stage_index = i
            if record:
                record.status = StageStatus.RUNNING
                record.started_at = datetime.now()
            self._store.save(state)

            log.info("stage_start", stage=stage.name, index=i)

            result = await stage.execute(state, mode, **stage_kwargs)

            # 将产物写入 state
            for key, path in result.artifacts.items():
                state.set_artifact(key, path)
                if record:
                    record.artifacts[key] = str(path)

            if result.decisions:
                if record:
                    record.decisions.extend(result.decisions)

            if not result.success:
                if record:
                    record.status = StageStatus.FAILED
                    record.error = result.error
                    record.completed_at = datetime.now()
                state.error = f"阶段 {stage.name} 失败: {result.error}"
                self._store.save(state)
                log.error("stage_failed", stage=stage.name, error=result.error)
                break

            if record:
                record.status = StageStatus.COMPLETED
                record.completed_at = datetime.now()

            self._store.save(state)
            log.info("stage_done", stage=stage.name, duration=f"{result.duration_seconds:.1f}s")

        state.completed = all(
            r.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
            for r in state.stages
        )
        state.last_updated = datetime.now()
        self._store.save(state)
        return state
