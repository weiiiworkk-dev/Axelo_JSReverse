from __future__ import annotations
import json
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis, AIHypothesis
from axelo.modes.base import ModeController
from axelo.ai.client import AIClient
from axelo.ai.context_builder import ContextBuilder
from axelo.ai.hypothesis import AIHypothesisOutput
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent.parent / "ai" / "prompts"


class AIAnalysisStage(PipelineStage):
    name = "s6_ai_analyze"
    description = "AI分析：基于静态+动态结果，由Claude归纳算法逻辑"

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client
        self._context_builder = ContextBuilder()
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def run(
        self, state: PipelineState, mode: ModeController,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None = None,
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        ai_dir = session_dir / "ai_context"
        ai_dir.mkdir(parents=True, exist_ok=True)

        # 组装上下文
        context_text = self._context_builder.build_analysis_context(
            static_results, dynamic, target.target_requests
        )

        # 渲染系统 prompt
        template = self._jinja.get_template("analyze_bundle.j2")
        system_prompt = template.render(context=context_text)

        user_msg = (
            f"目标网站: {target.url}\n"
            f"逆向目标: {target.interaction_goal}\n\n"
            "请分析上述 JS 代码和执行轨迹，识别 Token/签名的生成算法，并给出详细的逆向结论。"
        )

        log.info("ai_analyze_start", session_id=state.session_id)

        ai_output: AIHypothesisOutput = await self._ai.analyze(
            system_prompt=system_prompt,
            user_message=user_msg,
            output_schema=AIHypothesisOutput,
            tool_name="hypothesis",
            log_dir=ai_dir,
        )

        # 转换为内部模型
        hypothesis = AIHypothesis(
            algorithm_description=ai_output.algorithm_description,
            generator_func_ids=ai_output.generator_func_ids,
            steps=ai_output.steps,
            inputs=ai_output.inputs,
            outputs=ai_output.outputs,
            codegen_strategy=ai_output.codegen_strategy,
            python_feasibility=ai_output.python_feasibility,
            confidence=ai_output.confidence,
            notes=ai_output.notes,
        )

        # 保存假设
        hypothesis_path = ai_dir / "hypothesis.json"
        hypothesis_path.write_text(hypothesis.model_dump_json(indent=2), encoding="utf-8")

        log.info(
            "ai_analyze_done",
            confidence=f"{hypothesis.confidence:.0%}",
            strategy=hypothesis.codegen_strategy,
        )

        # 决策：审阅 AI 假设
        algo_preview = hypothesis.algorithm_description[:300]
        steps_preview = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(hypothesis.steps[:5]))

        options = [
            "接受假设，生成代码",
            "切换策略：Python重写",
            "切换策略：JS桥接",
            "跳过代码生成",
        ]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.OVERRIDE_HYPOTHESIS,
            prompt=f"AI 分析完成（置信度 {hypothesis.confidence:.0%}），请审阅算法假设：",
            options=options,
            artifact_path=hypothesis_path,
            context_summary=f"算法描述: {algo_preview}\n\n步骤:\n{steps_preview}",
            default="接受假设，生成代码",
        )

        outcome = await mode.gate(decision, state)

        # 根据选择调整策略
        if outcome == options[1]:
            hypothesis.codegen_strategy = "python_reconstruct"
        elif outcome == options[2]:
            hypothesis.codegen_strategy = "js_bridge"
        elif outcome == options[3]:
            hypothesis = None

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"hypothesis": hypothesis_path},
            decisions=[decision],
            summary=f"AI分析完成，置信度 {ai_output.confidence:.0%}，策略: {ai_output.codegen_strategy}",
            next_input={"hypothesis": hypothesis, "static_results": static_results, "target": target, "dynamic": dynamic},
        )
