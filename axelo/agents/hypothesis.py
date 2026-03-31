from __future__ import annotations
from axelo.agents.base import BaseAgent
from axelo.agents.scanner import ScanReport
from axelo.ai.context_builder import ContextBuilder
from axelo.ai.hypothesis import AIHypothesisOutput
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis, AIHypothesis
from axelo.models.target import TargetSite
from axelo.memory.retriever import MemoryRetriever
import structlog

log = structlog.get_logger()

HYPOTHESIS_SYSTEM = """你是一位 JS 逆向假设生成器（Hypothesis Agent）。

你的工作是基于充分的证据，归纳签名/Token 的生成算法。

## 核心原则
1. **证据优先**：每个结论必须有对应的代码片段或 Hook 记录支撑
2. **步骤清晰**：算法步骤要有序、可操作
3. **可行性诚实**：如果依赖浏览器特性（Canvas/WebGL/Device），明确指出应用 js_bridge 策略
4. **置信度校准**：有充分证据才给高置信度，不要过度自信

## 判断 codegen_strategy
- python_reconstruct：仅使用标准加密（hashlib/hmac/base64），feasibility > 0.8
- js_bridge：依赖 WebCrypto/Canvas/fingerprint/复杂浏览器API，feasibility < 0.6

## 类似经验参考
{memory_context}
"""


class HypothesisAgent(BaseAgent):
    """
    核心推理角色：基于静态+动态+记忆，生成算法假设。
    使用最强模型（Opus），因为这是准确性最关键的步骤。
    """
    role = "hypothesis"
    default_model = "claude-opus-4-6"

    def __init__(self, *args, retriever: MemoryRetriever, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._context_builder = ContextBuilder()

    async def generate(
        self,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        scan_report: ScanReport | None,
    ) -> AIHypothesis:
        # 查询历史经验
        memory_ctx = self._retriever.query_for_url(target.url, target.interaction_goal)
        memory_text = _format_memory(memory_ctx)

        system_prompt = HYPOTHESIS_SYSTEM.format(memory_context=memory_text)

        # 组装完整上下文
        context = self._context_builder.build_analysis_context(
            static_results, dynamic, target.target_requests
        )

        if scan_report:
            context = f"## Scanner 预扫描报告\n难度预估: {scan_report.estimated_difficulty}\n" \
                      f"关键函数: {scan_report.interesting_functions}\n\n" + context

        client = self._build_client()
        output: AIHypothesisOutput = await client.analyze(
            system_prompt=system_prompt,
            user_message=f"目标: {target.interaction_goal}\n\n{context}",
            output_schema=AIHypothesisOutput,
            tool_name="hypothesis",
            max_tokens=8192,
        )

        self._cost.add_ai_call(
            model=self._select_model(),
            input_tok=len(context) // 4,
            output_tok=500,
            stage="hypothesis",
        )

        hypothesis = AIHypothesis(
            algorithm_description=output.algorithm_description,
            generator_func_ids=output.generator_func_ids,
            steps=output.steps,
            inputs=output.inputs,
            outputs=output.outputs,
            codegen_strategy=output.codegen_strategy,
            python_feasibility=output.python_feasibility,
            confidence=output.confidence,
            notes=output.notes,
        )

        log.info("hypothesis_done", confidence=f"{hypothesis.confidence:.0%}", strategy=hypothesis.codegen_strategy)
        return hypothesis


def _format_memory(ctx: dict) -> str:
    parts = []
    if ctx.get("known_pattern"):
        p = ctx["known_pattern"]
        parts.append(f"已知站点模式: 算法={p.get('algorithm_type')}, 难度={p.get('difficulty')}, "
                     f"成功{p.get('success_count', 0)}次")
    if ctx.get("similar_sessions"):
        parts.append(f"相似历史案例 {len(ctx['similar_sessions'])} 个，均已验证")
    if ctx.get("suggested_templates"):
        names = [t.get("name") for t in ctx["suggested_templates"]]
        parts.append(f"推荐模板: {names}")
    return "\n".join(parts) if parts else "（无历史经验）"
