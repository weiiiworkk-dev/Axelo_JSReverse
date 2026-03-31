from __future__ import annotations
import structlog
from axelo.models.pipeline import Decision, PipelineState
from axelo.modes.base import ModeController

log = structlog.get_logger()


class AutoMode(ModeController):
    """
    全自动模式：所有决策使用 default 值，不阻塞。
    所有决策记录到结构化日志，供事后审计。
    """
    name = "auto"

    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        return True

    async def gate(self, decision: Decision, state: PipelineState) -> str:
        outcome = decision.default or (decision.options[0] if decision.options else "y")
        log.info(
            "auto_decision",
            session_id=state.session_id,
            stage=decision.stage,
            decision_type=decision.decision_type.value,
            outcome=outcome,
            decision_id=decision.decision_id,
        )
        decision.outcome = outcome
        decision.rationale = "auto mode default"
        return outcome
