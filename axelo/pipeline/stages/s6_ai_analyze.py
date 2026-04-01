from __future__ import annotations

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

from axelo.ai.client import AIClient
from axelo.ai.context_builder import ContextBuilder
from axelo.ai.hypothesis import AIHypothesisOutput
from axelo.analysis import build_signature_spec
from axelo.config import settings
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent.parent / "ai" / "prompts"


class AIAnalysisStage(PipelineStage):
    name = "s6_ai_analyze"
    description = "Use AI to synthesize the signing algorithm and build a structured signature spec."

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client
        self._context_builder = ContextBuilder()
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None = None,
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        ai_dir = session_dir / "ai_context"
        ai_dir.mkdir(parents=True, exist_ok=True)

        context_text = self._context_builder.build_analysis_context(static_results, dynamic, target.target_requests)
        template = self._jinja.get_template("analyze_bundle.j2")
        system_prompt = template.render(context=context_text, target=target)

        ai_output: AIHypothesisOutput = await self._ai.analyze(
            system_prompt=system_prompt,
            user_message=f"Target website: {target.url}\nGoal: {target.interaction_goal}",
            output_schema=AIHypothesisOutput,
            tool_name="hypothesis",
            log_dir=ai_dir,
        )

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
        hypothesis.signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)

        hypothesis_path = ai_dir / "hypothesis.json"
        hypothesis_path.write_text(hypothesis.model_dump_json(indent=2), encoding="utf-8")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.OVERRIDE_HYPOTHESIS,
            prompt=f"AI analysis finished with confidence {hypothesis.confidence:.0%}. Continue?",
            options=["accept", "force_python", "force_bridge", "skip_codegen"],
            artifact_path=hypothesis_path,
            context_summary=hypothesis.algorithm_description[:300],
            default="accept",
        )
        outcome = await mode.gate(decision, state)

        if outcome == "force_python":
            hypothesis.codegen_strategy = "python_reconstruct"
        elif outcome == "force_bridge":
            hypothesis.codegen_strategy = "js_bridge"
        elif outcome == "skip_codegen":
            hypothesis = None

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"hypothesis": hypothesis_path},
            decisions=[decision],
            summary=f"AI analysis complete, strategy={ai_output.codegen_strategy}",
            next_input={"hypothesis": hypothesis, "static_results": static_results, "target": target, "dynamic": dynamic},
        )
