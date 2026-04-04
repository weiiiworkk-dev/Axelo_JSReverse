from __future__ import annotations

from axelo.agents.verifier_agent import VerificationAnalysis, VerifierAgent
from axelo.ai.client import AIClient
from axelo.config import settings
from axelo.cost import CostBudget, CostRecord
from axelo.models.analysis import AIHypothesis
from axelo.models.codegen import GeneratedCode
from axelo.models.pipeline import PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage
from axelo.verification.engine import VerificationResult


class VerifyStage(PipelineStage):
    name = "s8_verify"
    description = "Run the canonical verification engine and persist the latest verification report."

    def __init__(
        self,
        ai_client: AIClient,
        cost: CostRecord,
        budget: CostBudget,
    ) -> None:
        self._ai = ai_client
        self._cost = cost
        self._budget = budget

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        generated: GeneratedCode | None = None,
        target: TargetSite | None = None,
        hypothesis: AIHypothesis | None = None,
        live_verify: bool | None = None,
        **_,
    ) -> StageResult:
        if generated is None or target is None or hypothesis is None:
            return StageResult(
                stage_name=self.name,
                success=True,
                summary="Verification skipped (missing generated code or hypothesis)",
            )

        session_dir = settings.session_dir(state.session_id)
        report_path = session_dir / "output" / "verify_report.txt"

        verifier = VerifierAgent(self._ai, self._cost, self._budget)
        verification: VerificationResult
        verification_analysis: VerificationAnalysis | None
        verification, verification_analysis = await verifier.verify_and_analyze(
            generated,
            target,
            hypothesis,
            live_verify=(
                target.compliance.allow_live_verification
                if live_verify is None
                else live_verify
            ),
        )
        generated.verified = verification.ok
        generated.verification_notes = verification.report
        report_path.write_text(verification.report, encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"verify_report": report_path},
            summary=(
                f"Verification {'passed' if verification.ok else 'failed'} "
                f"(score={verification.score:.2f}, attempts={verification.attempts})"
            ),
            next_input={
                "generated": generated,
                "verification": verification,
                "verification_analysis": verification_analysis,
            },
        )
