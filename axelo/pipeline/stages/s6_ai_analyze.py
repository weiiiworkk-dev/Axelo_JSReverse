from __future__ import annotations

import json

from axelo.agents.hypothesis import HypothesisAgent
from axelo.agents.scanner import ScannerAgent
from axelo.analysis import build_signature_spec
from axelo.config import settings
from axelo.models.analysis import AnalysisResult
from axelo.models.pipeline import StageResult


class AIAnalysisStage:
    def __init__(self, ai_client, cost, budget, retriever) -> None:
        self._ai_client = ai_client
        self._cost = cost
        self._budget = budget
        self._retriever = retriever

    async def execute(self, state, _mode, *, target, static_results, dynamic=None):
        out_dir = settings.workspace / "sessions" / state.session_id / "ai_context"
        out_dir.mkdir(parents=True, exist_ok=True)
        scanner = ScannerAgent(self._ai_client, self._cost, self._budget, self._retriever)
        scan_report = await scanner.scan(target, static_results)
        (out_dir / "scan_report.json").write_text(scan_report.model_dump_json(indent=2), encoding="utf-8")

        if target.execution_plan and target.execution_plan.ai_mode == "scanner_only":
            analysis = AnalysisResult(
                session_id=state.session_id,
                static=static_results,
                dynamic=dynamic,
                ai_hypothesis=None,
                ready_for_codegen=False,
                analysis_notes=scan_report.quick_verdict,
            )
            (out_dir / "analysis_result.json").write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
            return StageResult(stage_name="s6_ai_analyze", success=True, next_input={"analysis": analysis, "hypothesis": None, "scan_report": scan_report})

        hypothesis_agent = HypothesisAgent(self._ai_client, self._cost, self._budget, self._retriever)
        hypothesis = await hypothesis_agent.generate(target, static_results, dynamic, scan_report)
        hypothesis.signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)
        (out_dir / "hypothesis.json").write_text(hypothesis.model_dump_json(indent=2), encoding="utf-8")
        analysis = AnalysisResult(
            session_id=state.session_id,
            static=static_results,
            dynamic=dynamic,
            ai_hypothesis=hypothesis,
            signature_spec=hypothesis.signature_spec,
            overall_confidence=hypothesis.confidence,
            ready_for_codegen=hypothesis.signature_spec.codegen_strategy != "manual_required",
        )
        (out_dir / "analysis_result.json").write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
        return StageResult(stage_name="s6_ai_analyze", success=True, next_input={"analysis": analysis, "hypothesis": hypothesis, "scan_report": scan_report})
