from __future__ import annotations

import structlog

from axelo.agents.base import BaseAgent
from axelo.agents.scanner import ScanReport
from axelo.ai.context_builder import ContextBuilder
from axelo.ai.hypothesis import AIHypothesisOutput
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.target import TargetSite

log = structlog.get_logger()

HYPOTHESIS_SYSTEM = """你是一位 JS 逆向假设生成器（Hypothesis Agent）。

## 类似经验参考
{memory_context}
"""


class HypothesisAgent(BaseAgent):
    role = "hypothesis"
    default_model = "claude-sonnet-4-6"

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
        memory_ctx = self._retriever.query_for_url(target.url, target.interaction_goal)
        memory_text = _format_memory(memory_ctx)
        context = self._context_builder.build_analysis_context(static_results, dynamic, target.target_requests)
        self.default_model = "claude-sonnet-4-6"
        if scan_report and scan_report.bundle_complexity in {"complex", "obfuscated"}:
            self.default_model = "claude-opus-4-6"
        if scan_report and scan_report.estimated_difficulty == "extreme":
            self.default_model = "claude-opus-4-6"

        if scan_report:
            context = (
                "## Scanner 预扫描报告\n"
                f"难度预估: {scan_report.estimated_difficulty}\n"
                f"关键函数: {scan_report.interesting_functions}\n\n"
                f"{context}"
            )
        if dynamic and dynamic.topology_summary:
            topology_block = "\n".join(f"- {item}" for item in dynamic.topology_summary[:5])
            context = f"## 已确认的数据流拓扑\n{topology_block}\n\n{context}"

        client = self._build_client()
        response = await client.analyze(
            system_prompt=HYPOTHESIS_SYSTEM.format(memory_context=memory_text),
            user_message=(
                f"目标: {target.interaction_goal}\n\n"
                "请基于已确认的数据流拓扑解释并补全语义，不要改写已确认的步骤顺序或输出字段。\n\n"
                f"{context}"
            ),
            output_schema=AIHypothesisOutput,
            tool_name="hypothesis",
            max_tokens=2048,   # Cost-E: average actual output ~1200 tokens
        )
        output = response.data

        self._cost.add_ai_call(
            model=response.model,
            input_tok=response.input_tokens,
            output_tok=response.output_tokens,
            stage="hypothesis",
        )

        hypothesis = AIHypothesis(
            algorithm_description=output.algorithm_description,
            generator_func_ids=output.generator_func_ids,
            steps=output.steps,
            inputs=output.inputs,
            outputs=output.outputs,
            family_id=output.family_id,
            codegen_strategy=output.codegen_strategy,
            python_feasibility=output.python_feasibility,
            confidence=output.confidence,
            notes=output.notes,
            secret_candidate="",
        )

        log.info("hypothesis_done", confidence=f"{hypothesis.confidence:.0%}", strategy=hypothesis.codegen_strategy)
        return hypothesis


def _format_memory(ctx: dict) -> str:
    parts: list[str] = []
    if ctx.get("known_pattern"):
        pattern = ctx["known_pattern"]
        parts.append(
            f"已知站点模式: 算法={pattern.get('algorithm_type')}, 难度={pattern.get('difficulty')}, "
            f"成功{pattern.get('success_count', 0)}次"
        )
    if ctx.get("similar_sessions"):
        parts.append(f"相似历史案例 {len(ctx['similar_sessions'])} 个，均已验证")
    if ctx.get("suggested_templates"):
        names = [item.get("name") for item in ctx["suggested_templates"]]
        parts.append(f"推荐模板: {names}")
    return "\n".join(parts) if parts else "（无历史经验）"
