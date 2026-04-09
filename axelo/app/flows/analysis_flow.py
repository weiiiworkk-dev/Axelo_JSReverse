from __future__ import annotations

import structlog

from axelo.ai.client import AIClient
from axelo.analysis.request_contracts import derive_capability_profile
from axelo.analysis import build_signature_spec
from axelo.analysis.family_detector import build_hypothesis_from_family, detect_signature_family
from axelo.analysis.observed_replay import build_hypothesis_from_observed_request
from axelo.app.artifacts import AnalysisArtifacts
from axelo.classifier.rules import classify
from axelo.config import settings
from axelo.models.analysis import AnalysisResult
from axelo.models.pipeline import Decision, DecisionType
from axelo.pipeline.stages import AIAnalysisStage, DynamicAnalysisStage

from ._common import artifact_map, execute_stage_with_metrics

log = structlog.get_logger()


class AnalysisFlow:
    def __init__(self, *, store, db, retriever, analysis_cache, routing_service) -> None:
        self._store = store
        self._db = db
        self._retriever = retriever
        self._analysis_cache = analysis_cache
        self._routing_service = routing_service

    async def run(self, ctx) -> AnalysisArtifacts | None:
        known_pattern = self._db.get_site_pattern(ctx.memory_ctx.get("domain", "")) if ctx.memory_ctx.get("known_pattern") else None
        ctx.difficulty = classify(ctx.target, ctx.static_results, known_pattern)
        ctx.result.difficulty = ctx.difficulty

        if ctx.difficulty.level == "extreme" and ctx.target.compliance.require_manual_for_extreme:
            ctx.analysis = AnalysisResult(session_id=ctx.sid, static=ctx.static_results, manual_review_required=True)
            ctx.state.workflow_status = "waiting_manual_review"
            ctx.state.manual_review_reason = "Extreme target requires manual review"
            self._store.save(ctx.state)
            ctx.target.trace = ctx.workflow.request_manual_review(
                ctx.sid,
                ctx.target.trace,
                "difficulty",
                summary=f"Extreme site classified: {ctx.difficulty.reasons}",
            )
            decision = Decision(
                stage="difficulty",
                decision_type=DecisionType.MANUAL_REVIEW,
                prompt="Target classified as extreme. Manual review is required before continuing.",
                options=["stop_for_manual_review", "force_continue"],
                default="stop_for_manual_review",
                context_summary=", ".join(ctx.difficulty.reasons),
            )
            outcome = await ctx.mode.gate(decision, ctx.state)
            if outcome != "force_continue":
                ctx.result.error = "manual review required for extreme target"
                return None
            ctx.state.workflow_status = "running"
            ctx.state.manual_review_reason = ""
            self._store.save(ctx.state)

        if self._routing_service.should_run_dynamic(ctx):
            dyn_stage = DynamicAnalysisStage()
            ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s5_dynamic", "running")
            ctx.state.current_stage_index = 4
            self._store.save(ctx.state)
            dyn_result = await execute_stage_with_metrics(
                ctx,
                dyn_stage,
                ctx.state,
                ctx.mode,
                target=ctx.target,
                static_results=ctx.static_results,
            )
            if not dyn_result.success:
                ctx.result.error = dyn_result.error
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s5_dynamic",
                    "failed",
                    summary=ctx.result.error or "",
                )
                return None
            ctx.dynamic = dyn_result.next_input.get("dynamic")
            ctx.cost.add_browser_session(stage="s5_dynamic")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s5_dynamic",
                "completed",
                summary=dyn_result.summary,
                artifacts=artifact_map(dyn_result.artifacts),
            )

        templates = self._retriever.get_all_templates()
        ctx.family_match = detect_signature_family(
            ctx.target,
            ctx.static_results,
            dynamic=ctx.dynamic,
            memory_ctx=ctx.memory_ctx,
            templates=templates,
        )
        ctx.analysis = AnalysisResult(
            session_id=ctx.sid,
            static=ctx.static_results,
            dynamic=ctx.dynamic,
            signature_family=ctx.family_match.family_id,
        )

        if self._routing_service.should_use_static_only(ctx):
            ctx.cost.set_route("static_only")
            ctx.analysis.overall_confidence = max(
                self._routing_service.top_static_confidence(ctx.static_results),
                ctx.family_match.confidence,
            )
            ctx.analysis.analysis_notes = "Static evidence was sufficient for discovery/archive output."
            if ctx.family_match.family_id != "unknown":
                ctx.hypothesis = build_hypothesis_from_family(ctx.family_match, ctx.target)
                ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
                ctx.analysis.ai_hypothesis = ctx.hypothesis
                ctx.analysis.signature_spec = ctx.hypothesis.signature_spec
            ctx.cost.set_stage_timing("s6_ai_analyze", 0, status="skipped", exit_reason="static_only")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s6_ai_analyze",
                "skipped",
                summary="Static-only route satisfied discovery/archive requirements",
            )
            self._analysis_cache.save(
                ctx.target,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                signature_family=ctx.family_match.family_id,
                template_name=ctx.family_match.template_name,
                signature_spec=ctx.analysis.signature_spec,
            )
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
                scan_report=ctx.scan_report,
            )

        if not ctx.governor.allow_ai(ctx.cost, ctx.target.execution_plan):
            if ctx.target.execution_plan and ctx.target.execution_plan.skip_codegen:
                ctx.cost.set_route("static_only")
                ctx.analysis.analysis_notes = "Budget exhausted before scanner stage; archived static evidence only."
                ctx.cost.set_stage_timing("s6_ai_analyze", 0, status="skipped", exit_reason="budget_exhausted")
                return AnalysisArtifacts(
                    difficulty=ctx.difficulty,
                    dynamic=ctx.dynamic,
                    family_match=ctx.family_match,
                    analysis=ctx.analysis,
                )
            ctx.result.error = "budget exhausted before AI analysis"
            return None

        if self._routing_service.should_use_template_codegen(ctx):
            ctx.cost.set_route("family_template")
            ctx.hypothesis = build_hypothesis_from_family(ctx.family_match, ctx.target)
            ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
            ctx.target.capability_profile = derive_capability_profile(
                ctx.target,
                contract=ctx.target.selected_contract,
                codegen_strategy=ctx.hypothesis.codegen_strategy,
            )
            ctx.analysis = AnalysisResult(
                session_id=ctx.sid,
                static=ctx.static_results,
                dynamic=ctx.dynamic,
                ai_hypothesis=ctx.hypothesis,
                signature_spec=ctx.hypothesis.signature_spec,
                overall_confidence=ctx.hypothesis.confidence,
                ready_for_codegen=True,
                manual_review_required=False,
                signature_family=ctx.family_match.family_id,
                analysis_notes="Family template selection satisfied codegen prerequisites.",
            )
            ctx.cost.set_stage_timing("s6_ai_analyze", 0, status="skipped", exit_reason="family_template")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s6_ai_analyze",
                "skipped",
                summary=f"Template-backed family detection: {ctx.family_match.family_id}",
            )
            self._analysis_cache.save(
                ctx.target,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                signature_family=ctx.family_match.family_id,
                template_name=ctx.family_match.template_name,
                signature_spec=ctx.hypothesis.signature_spec,
            )
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
            )

        if self._routing_service.should_use_family_codegen(ctx):
            ctx.cost.set_route("bridge_template")
            ctx.hypothesis = build_hypothesis_from_family(ctx.family_match, ctx.target)
            ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
            ctx.target.capability_profile = derive_capability_profile(
                ctx.target,
                contract=ctx.target.selected_contract,
                codegen_strategy=ctx.hypothesis.codegen_strategy,
            )
            ctx.analysis = AnalysisResult(
                session_id=ctx.sid,
                static=ctx.static_results,
                dynamic=ctx.dynamic,
                ai_hypothesis=ctx.hypothesis,
                signature_spec=ctx.hypothesis.signature_spec,
                overall_confidence=ctx.hypothesis.confidence,
                ready_for_codegen=True,
                manual_review_required=False,
                signature_family=ctx.family_match.family_id,
                analysis_notes="Bridge template selection satisfied codegen prerequisites.",
            )
            ctx.cost.set_stage_timing("s6_ai_analyze", 0, status="skipped", exit_reason="bridge_template")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s6_ai_analyze",
                "skipped",
                summary=f"Family-backed bridge generation: {ctx.family_match.family_id}",
            )
            self._analysis_cache.save(
                ctx.target,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                signature_family=ctx.family_match.family_id,
                template_name=ctx.family_match.template_name,
                signature_spec=ctx.hypothesis.signature_spec,
            )
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
            )

        if self._routing_service.should_use_observed_replay(ctx):
            ctx.cost.set_route("contract_replay")
            ctx.hypothesis = build_hypothesis_from_observed_request(ctx.target)
            ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
            ctx.target.capability_profile = derive_capability_profile(
                ctx.target,
                contract=ctx.target.selected_contract,
                codegen_strategy=ctx.hypothesis.codegen_strategy,
            )
            ctx.analysis = AnalysisResult(
                session_id=ctx.sid,
                static=ctx.static_results,
                dynamic=ctx.dynamic,
                ai_hypothesis=ctx.hypothesis,
                signature_spec=ctx.hypothesis.signature_spec,
                overall_confidence=ctx.hypothesis.confidence,
                ready_for_codegen=True,
                manual_review_required=False,
                signature_family=ctx.family_match.family_id,
                analysis_notes="Contract replay template satisfied codegen prerequisites.",
            )
            ctx.cost.set_stage_timing("s6_ai_analyze", 0, status="skipped", exit_reason="contract_replay")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s6_ai_analyze",
                "skipped",
                summary="Contract replay template selected",
            )
            self._analysis_cache.save(
                ctx.target,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                signature_family=ctx.family_match.family_id,
                template_name=ctx.hypothesis.template_name,
                signature_spec=ctx.hypothesis.signature_spec,
            )
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
            )

        if not self._routing_service.choose_route(ctx).requires_ai:
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
                scan_report=ctx.scan_report,
            )

        # 优先使用 DeepSeek V3，如果失败则 fallback 到 Claude
        # 检查 DeepSeek API key 是否可用
        from axelo.ai.dual_model_client import DualModelOrchestrator
        
        orchestrator = None
        if settings.deepseek_api_key:
            try:
                orchestrator = DualModelOrchestrator(
                    deepseek_key=settings.deepseek_api_key,
                    anthropic_key=settings.anthropic_api_key,
                    enable_fallback=True
                )
                log.info("using_deepseek_v3_primary")
            except Exception as e:
                log.warning("deepseek_init_failed_using_claude", error=str(e))
                orchestrator = None
        
        # 如果没有 DeepSeek，回退到纯 Claude
        if orchestrator is None:
            log.info("using_claude_direct")
        
        # 创建 AI Client (优先 DeepSeek)
        if orchestrator and orchestrator._deepseek_v3:
            # 使用 DualModelOrchestrator 作为 AI 客户端
            ctx.ai_client = orchestrator
            ctx.ai_client_name = "deepseek-v3"
        else:
            # 回退到 Claude
            ctx.ai_client = AIClient(api_key=settings.anthropic_api_key, model=settings.model)
            ctx.ai_client_name = "claude"
        
        ai_stage = AIAnalysisStage(ctx.ai_client, ctx.cost, ctx.budget, self._retriever)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s6_ai_analyze", "running")
        ctx.state.current_stage_index = 5
        self._store.save(ctx.state)
        ai_result = await execute_stage_with_metrics(
            ctx,
            ai_stage,
            ctx.state,
            ctx.mode,
            target=ctx.target,
            static_results=ctx.static_results,
            dynamic=ctx.dynamic,
        )
        if not ai_result.success:
            ctx.result.error = ai_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s6_ai_analyze",
                "failed",
                summary=ctx.result.error or "",
            )
            return None

        ctx.analysis = ai_result.next_input.get("analysis", ctx.analysis)
        ctx.hypothesis = ai_result.next_input.get("hypothesis")
        ctx.scan_report = ai_result.next_input.get("scan_report")
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s6_ai_analyze",
            "completed",
            summary=ai_result.summary,
            artifacts=artifact_map(ai_result.artifacts),
        )

        if ctx.analysis is not None and ctx.analysis.signature_family == "unknown":
            ctx.analysis.signature_family = ctx.family_match.family_id
        if ctx.target.execution_plan and ctx.target.execution_plan.ai_mode == "scanner_only":
            ctx.cost.set_route("scanner_only")
            self._analysis_cache.save(
                ctx.target,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                signature_family=ctx.family_match.family_id,
                template_name=ctx.family_match.template_name,
                scan_report=ctx.scan_report.model_dump(mode="json") if hasattr(ctx.scan_report, "model_dump") else None,
                signature_spec=ctx.analysis.signature_spec if ctx.analysis else None,
            )
            if ctx.analysis is None:
                ctx.result.error = "AI analysis did not produce a usable hypothesis"
                return None
            return AnalysisArtifacts(
                difficulty=ctx.difficulty,
                dynamic=ctx.dynamic,
                family_match=ctx.family_match,
                analysis=ctx.analysis,
                hypothesis=ctx.hypothesis,
                scan_report=ctx.scan_report,
            )

        if ctx.analysis is None or ctx.hypothesis is None:
            ctx.result.error = "AI analysis did not produce a usable hypothesis"
            return None

        ctx.target.capability_profile = derive_capability_profile(
            ctx.target,
            contract=ctx.target.selected_contract,
            codegen_strategy=ctx.hypothesis.codegen_strategy,
        )
        ctx.cost.set_route("full_ai_unknown_family")
        if self._routing_service.requires_low_confidence_confirmation(ctx) and ctx.mode_name != "auto":
            decision = Decision(
                stage="master",
                decision_type=DecisionType.APPROVE_STAGE,
                prompt=f"AI confidence is low ({ctx.hypothesis.confidence:.0%}). Continue with code generation?",
                options=["continue", "stop"],
                default="continue",
            )
            outcome = await ctx.mode.gate(decision, ctx.state)
            if outcome == "stop":
                ctx.result.error = "user declined low-confidence result"
                return None

        if ctx.analysis.manual_review_required or (
            ctx.analysis.signature_spec and ctx.analysis.signature_spec.codegen_strategy == "manual_required"
        ):
            ctx.result.error = "signature spec requires manual implementation"
            ctx.target.trace = ctx.workflow.request_manual_review(
                ctx.sid,
                ctx.target.trace,
                "signature_spec",
                summary="Structured analysis marked this target as manual_required",
            )
            return None

        self._analysis_cache.save(
            ctx.target,
            bundle_hashes=ctx.bundle_hashes,
            static_results=ctx.static_results,
            signature_family=ctx.analysis.signature_family,
            template_name=ctx.hypothesis.template_name,
            scan_report=ctx.scan_report.model_dump(mode="json") if hasattr(ctx.scan_report, "model_dump") else None,
            signature_spec=ctx.analysis.signature_spec,
        )
        return AnalysisArtifacts(
            difficulty=ctx.difficulty,
            dynamic=ctx.dynamic,
            family_match=ctx.family_match,
            analysis=ctx.analysis,
            hypothesis=ctx.hypothesis,
            scan_report=ctx.scan_report,
        )
