from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from axelo.agents.base import BaseAgent
from axelo.models.analysis import AIHypothesis
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite
from axelo.verification.engine import VerificationEngine, VerificationResult
import structlog

log = structlog.get_logger()


class VerificationAnalysis(BaseModel):
    """AI 分析验证失败原因并给出修复建议"""
    failure_type: str = Field(description="失败类型：wrong_algorithm/missing_field/encoding_error/timing/env_dependency")
    root_cause: str = Field(description="根本原因分析（1-2句话）")
    fix_suggestion: str = Field(description="修复建议：具体的代码修改方向")
    retry_strategy: str = Field(description="重试策略：patch_code/switch_to_bridge/add_dynamic_analysis/give_up")
    confidence: float = Field(ge=0, le=1, description="修复成功可能性评估")


VERIFIER_SYSTEM = """你是一位验证分析专家（Verifier Agent）。

你的工作是分析生成代码的验证失败原因，并给出精确的修复方向。

输入：验证报告 + 原始算法假设 + 生成代码片段
输出：失败根因 + 可操作的修复建议

常见失败类型：
- wrong_algorithm：算法逻辑有误（如 HMAC key 错误、参数顺序错误）
- missing_field：遗漏了某些必要的请求头/参数
- encoding_error：编码方式不对（hex vs base64，大小写等）
- timing：时间戳精度问题（秒 vs 毫秒）
- env_dependency：依赖浏览器环境变量，需要改为 js_bridge
"""


class VerifierAgent(BaseAgent):
    """
    验证角色：运行验证引擎，失败时用 AI 分析根因并给出修复方向。
    """
    role = "verifier"
    default_model = "claude-sonnet-4-6"

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
            # 用 AI 分析失败原因
            script_preview = ""
            if generated.crawler_script_path and generated.crawler_script_path.exists():
                script_preview = generated.crawler_script_path.read_text(encoding="utf-8")[:1500]

            context = (
                f"验证报告:\n{result.report}\n\n"
                f"重试原因: {result.retry_reason}\n\n"
                f"算法假设:\n{hypothesis.algorithm_description}\n\n"
                f"代码片段:\n```python\n{script_preview}\n```"
            )

            client = self._build_client()
            try:
                analysis = await client.analyze(
                    system_prompt=VERIFIER_SYSTEM,
                    user_message=f"分析以下验证失败：\n\n{context}",
                    output_schema=VerificationAnalysis,
                    tool_name="verification_analysis",
                    max_tokens=2048,
                )
                self._cost.add_ai_call(
                    model=self._select_model(),
                    input_tok=len(context) // 4,
                    output_tok=300,
                    stage="verifier",
                )
                log.info("verifier_analysis", failure_type=analysis.failure_type, strategy=analysis.retry_strategy)
            except Exception as e:
                log.warning("verifier_ai_failed", error=str(e))

        return result, analysis
