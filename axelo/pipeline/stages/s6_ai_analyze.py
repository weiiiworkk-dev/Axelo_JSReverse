from __future__ import annotations

from axelo.agents.hypothesis import HypothesisAgent
from axelo.agents.scanner import ScanReport, ScannerAgent
from axelo.ai.client import AIClient
from axelo.analysis import build_signature_spec
from axelo.config import settings
from axelo.cost import CostBudget, CostRecord
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AnalysisResult, DynamicAnalysis, StaticAnalysis
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage


class AIAnalysisStage(PipelineStage):
    name = "s6_ai_analyze"
    description = "Scan evidence, build an AI hypothesis, and derive the canonical SignatureSpec."

    def __init__(
        self,
        ai_client: AIClient,
        cost: CostRecord,
        budget: CostBudget,
        retriever: MemoryRetriever,
    ) -> None:
        self._ai = ai_client
        self._cost = cost
        self._budget = budget
        self._retriever = retriever

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

        scanner = ScannerAgent(
            self._ai,
            self._cost,
            self._budget,
            retriever=self._retriever,
        )
        scan_report: ScanReport = await scanner.scan(target, static_results)
        scan_report_path = ai_dir / "scan_report.json"
        scan_report_path.write_text(scan_report.model_dump_json(indent=2), encoding="utf-8")

        hypothesis_agent = HypothesisAgent(
            self._ai,
            self._cost,
            self._budget,
            retriever=self._retriever,
        )
        hypothesis = await hypothesis_agent.generate(target, static_results, dynamic, scan_report)
        hypothesis.signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)

        analysis = AnalysisResult(
            session_id=state.session_id,
            static=static_results,
            dynamic=dynamic,
            ai_hypothesis=hypothesis,
            signature_spec=hypothesis.signature_spec,
            overall_confidence=hypothesis.confidence,
            ready_for_codegen=(
                hypothesis.confidence > 0.5
                and hypothesis.signature_spec.codegen_strategy != "manual_required"
            ),
            manual_review_required=hypothesis.signature_spec.codegen_strategy == "manual_required",
        )

        hypothesis_path = ai_dir / "hypothesis.json"
        hypothesis_path.write_text(hypothesis.model_dump_json(indent=2), encoding="utf-8")
        analysis_path = ai_dir / "analysis_result.json"
        analysis_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.OVERRIDE_HYPOTHESIS,
            prompt=f"AI analysis finished with confidence {hypothesis.confidence:.0%}. Continue?",
            options=["accept", "force_python", "force_bridge"],
            artifact_path=hypothesis_path,
            context_summary=hypothesis.algorithm_description[:300],
            default="accept",
        )
        outcome = await mode.gate(decision, state)

        if outcome == "force_python":
            hypothesis.codegen_strategy = "python_reconstruct"
        elif outcome == "force_bridge":
            hypothesis.codegen_strategy = "js_bridge"

        if outcome in {"force_python", "force_bridge"}:
            hypothesis.signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)
            analysis.ai_hypothesis = hypothesis
            analysis.signature_spec = hypothesis.signature_spec
            analysis.overall_confidence = hypothesis.confidence
            analysis.ready_for_codegen = (
                hypothesis.confidence > 0.5
                and hypothesis.signature_spec.codegen_strategy != "manual_required"
            )
            analysis.manual_review_required = (
                hypothesis.signature_spec.codegen_strategy == "manual_required"
            )
            hypothesis_path.write_text(hypothesis.model_dump_json(indent=2), encoding="utf-8")
            analysis_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={
                "scan_report": scan_report_path,
                "hypothesis": hypothesis_path,
                "analysis_result": analysis_path,
            },
            decisions=[decision],
            summary=(
                f"AI analysis complete, difficulty={scan_report.estimated_difficulty}, "
                f"strategy={analysis.signature_spec.codegen_strategy if analysis.signature_spec else hypothesis.codegen_strategy}"
            ),
            next_input={
                "analysis": analysis,
                "hypothesis": hypothesis,
                "scan_report": scan_report,
                "static_results": static_results,
                "target": target,
                "dynamic": dynamic,
            },
        )
