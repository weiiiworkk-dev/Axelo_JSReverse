from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from axelo.agents.base import BaseAgent
from axelo.models.analysis import AIHypothesis
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite
from axelo.verification.engine import VerificationEngine, VerificationResult

log = structlog.get_logger()


class VerificationAnalysis(BaseModel):
    failure_type: str = Field(description="wrong_algorithm/missing_field/encoding_error/timing/env_dependency")
    root_cause: str = Field(description="One or two sentences on the root cause")
    fix_suggestion: str = Field(description="Concrete implementation direction")
    retry_strategy: str = Field(description="patch_code/switch_to_bridge/add_dynamic_analysis/give_up")
    confidence: float = Field(ge=0, le=1, description="Estimated fix success probability")


VERIFIER_SYSTEM = """你是一位验证分析专家（Verifier Agent）。

你的工作是分析生成代码的验证失败原因，并给出精确的修复方向。
"""


class VerifierAgent(BaseAgent):
    role = "verifier"
    default_model = "deepseek-chat"

    async def verify_and_analyze(
        self,
        generated: GeneratedCode,
        target: TargetSite,
        hypothesis: AIHypothesis,
        live_verify: bool = True,
    ) -> tuple[VerificationResult, VerificationAnalysis | None]:
        engine = VerificationEngine()
        result = await engine.verify(generated, target, live_verify=live_verify)

        analysis: VerificationAnalysis | None = None
        if not result.ok and result.retry_reason:
            script_preview = ""
            if generated.crawler_script_path and generated.crawler_script_path.exists():
                script_preview = generated.crawler_script_path.read_text(encoding="utf-8")[:1500]
            replay_status = result.replay.status_code if result.replay is not None else 0

            context = (
                f"验证摘要:\nstatus={replay_status} retry_reason={result.retry_reason or 'n/a'} "
                f"risk={result.risk_control_reason or 'n/a'}\n\n"
                f"重试原因: {result.retry_reason}\n\n"
                f"算法假设:\n{hypothesis.algorithm_description}\n\n"
                f"代码片段:\n```python\n{script_preview}\n```"
            )

            client = self._build_client()
            try:
                response = await client.analyze(
                    system_prompt=VERIFIER_SYSTEM,
                    user_message=f"分析以下验证失败：\n\n{context}",
                    output_schema=VerificationAnalysis,
                    tool_name="verification_analysis",
                    max_tokens=512,   # Cost-E: VerificationAnalysis is structured + small
                )
                analysis = response.data
                self._cost.add_ai_call(
                    model=response.model,
                    input_tok=response.input_tokens,
                    output_tok=response.output_tokens,
                    stage="verifier",
                )
                log.info("verifier_analysis", failure_type=analysis.failure_type, strategy=analysis.retry_strategy)
            except Exception as exc:
                log.warning("verifier_ai_failed", error=str(exc))

        return result, analysis
