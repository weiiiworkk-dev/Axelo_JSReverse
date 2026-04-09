from __future__ import annotations

from axelo.agents.verifier_agent import VerifierAgent
from axelo.config import settings
from axelo.models.pipeline import StageResult


class VerifyStage:
    def __init__(self, ai_client, cost, budget) -> None:
        self._agent = VerifierAgent(ai_client, cost, budget)

    async def execute(self, state, _mode, *, generated, target, hypothesis, live_verify=True):
        verification, analysis = await self._agent.verify_and_analyze(generated, target, hypothesis, live_verify=live_verify)
        generated.verified = verification.ok
        generated.verification_notes = verification.report
        out_dir = settings.workspace / "sessions" / state.session_id / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "verify_report.txt").write_text(verification.report, encoding="utf-8")
        return StageResult(
            stage_name="s8_verify",
            success=True,
            summary=verification.report,
            next_input={
                "generated": generated,
                "verification": verification,
                "verification_analysis": analysis,
            },
        )
