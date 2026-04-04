from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import structlog

from axelo.agents.memory_writer_agent import MemoryWriterAgent
from axelo.ai.client import AIClient
from axelo.analysis import ASTAnalyzer, build_signature_spec
from axelo.classifier.rules import DifficultyScore, classify
from axelo.config import settings
from axelo.cost import CostBudget, CostGovernor, CostRecord
from axelo.js_tools.runner import NodeRunner
from axelo.memory.db import MemoryDB
from axelo.memory.retriever import MemoryRetriever
from axelo.memory.vector_store import VectorStore
from axelo.memory.writer import MemoryWriter
from axelo.models.analysis import AIHypothesis, AnalysisResult, DynamicAnalysis, StaticAnalysis
from axelo.models.codegen import GeneratedCode
from axelo.models.execution import ExecutionPlan, ExecutionTier, VerificationMode
from axelo.models.pipeline import Decision, DecisionType, PipelineState
from axelo.models.target import BrowserProfile, TargetSite
from axelo.modes.registry import create_mode
from axelo.orchestrator.workflow_runtime import WorkflowRuntime
from axelo.planner import Planner
from axelo.patterns.common import match_profile
from axelo.policies import resolve_runtime_policy
from axelo.storage import AdapterRegistry, SessionStore, WorkflowStore
from axelo.telemetry import write_run_report
from axelo.verification.engine import VerificationEngine

from axelo.pipeline.stages import (
    AIAnalysisStage,
    CodeGenStage,
    CrawlStage,
    DeobfuscateStage,
    DynamicAnalysisStage,
    FetchStage,
    StaticAnalysisStage,
    VerifyStage,
)

log = structlog.get_logger()


@dataclass
class MasterResult:
    session_id: str
    url: str
    difficulty: DifficultyScore | None = None
    analysis: AnalysisResult | None = None
    generated: GeneratedCode | None = None
    verified: bool = False
    cost: CostRecord | None = None
    output_dir: Path | None = None
    report_path: Path | None = None
    execution_plan: ExecutionPlan | None = None
    adapter_reused: bool = False
    error: str | None = None
    completed: bool = False


@dataclass
class MasterRunContext:
    sid: str
    mode_name: str
    mode: object
    cost: CostRecord
    budget: CostBudget
    governor: CostGovernor
    result: MasterResult
    state: PipelineState
    workflow: WorkflowRuntime
    target: TargetSite
    runtime_policy: object
    session_dir: Path
    output_dir: Path
    memory_ctx: dict[str, object]
    adapter_candidate: object | None = None
    analysis: AnalysisResult | None = None
    generated: GeneratedCode | None = None
    verified: bool = False
    difficulty: DifficultyScore | None = None
    static_results: dict[str, StaticAnalysis] = field(default_factory=dict)
    dynamic: DynamicAnalysis | None = None
    hypothesis: AIHypothesis | None = None
    ai_client: AIClient | None = None


class MasterOrchestrator:
    """Primary orchestrator for the current Axelo runtime."""

    def __init__(self) -> None:
        self._store = SessionStore(settings.sessions_dir)
        self._workflow_store = WorkflowStore(settings.sessions_dir)
        self._adapter_registry = AdapterRegistry(settings.workspace)
        self._planner = Planner(self._adapter_registry)
        mem_dir = settings.workspace / "memory"
        self._db = MemoryDB(mem_dir / "axelo.db")
        self._vs = VectorStore(mem_dir / "vectors")
        self._retriever = MemoryRetriever(self._db, self._vs)
        self._mem_writer = MemoryWriter(self._db, self._vs)

    async def run(
        self,
        url: str,
        goal: str,
        mode_name: str = "interactive",
        session_id: str | None = None,
        budget_usd: float = 2.0,
        resume: bool = False,
        known_endpoint: str = "",
        antibot_type: str = "unknown",
        requires_login: bool | None = None,
        output_format: str = "print",
        crawl_rate: str = "standard",
    ) -> MasterResult:
        ctx = await self._initialize_run_context(
            url=url,
            goal=goal,
            mode_name=mode_name,
            session_id=session_id,
            budget_usd=budget_usd,
            resume=resume,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
        )

        short_circuit = await self._maybe_short_circuit(ctx)
        if short_circuit is not None:
            return await self._finalize_run(ctx, short_circuit)

        runner = NodeRunner(settings.node_bin)
        await runner.start()
        ctx.cost.add_node_call()

        try:
            target = ctx.target
            target.trace = ctx.workflow.checkpoint(ctx.sid, target.trace, "master", "started", summary="Run started")
            ctx.state.workflow_status = "running"
            self._store.save(ctx.state)

            ast_analyzer = ASTAnalyzer(runner)
            if not await self._run_discovery_stages(ctx, runner=runner, ast_analyzer=ast_analyzer):
                return await self._finalize_run(ctx, False)
            if not await self._run_analysis_stages(ctx):
                return await self._finalize_run(ctx, False)
            if not await self._run_codegen_and_verify(ctx):
                return await self._finalize_run(ctx, False)
        except Exception as exc:
            ctx.result.error = str(exc)
            ctx.state.workflow_status = "failed"
            ctx.state.error = ctx.result.error
            self._store.save(ctx.state)
            ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "master", "failed", summary=ctx.result.error)
            return await self._finalize_run(ctx, False)
        finally:
            await runner.stop()

        await self._write_memory(ctx)
        return await self._finalize_run(ctx, True)

    async def _initialize_run_context(
        self,
        *,
        url: str,
        goal: str,
        mode_name: str,
        session_id: str | None,
        budget_usd: float,
        resume: bool,
        known_endpoint: str,
        antibot_type: str,
        requires_login: bool | None,
        output_format: str,
        crawl_rate: str,
    ) -> MasterRunContext:
        sid = session_id or str(uuid.uuid4())[:8]
        mode = create_mode(mode_name)
        cost = CostRecord(session_id=sid)
        budget = CostBudget(max_usd=budget_usd)
        governor = CostGovernor(max_usd=budget_usd)
        result = MasterResult(session_id=sid, url=url)

        session_dir = settings.session_dir(sid)
        session_dir.mkdir(parents=True, exist_ok=True)
        output_dir = session_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        state = PipelineState(session_id=sid, mode=mode_name)
        if resume:
            loaded = self._store.load(sid)
            if loaded:
                state = loaded
                log.info("session_resumed", session_id=sid, workflow_status=state.workflow_status)
        self._store.save(state)

        workflow = WorkflowRuntime(self._workflow_store)
        trace = workflow.load_or_create(sid)

        target = TargetSite(
            url=url,
            session_id=sid,
            interaction_goal=goal,
            browser_profile=BrowserProfile(),
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
            trace=trace,
        )
        runtime_policy = resolve_runtime_policy(target)
        target.browser_profile = runtime_policy.apply_to_profile(target.browser_profile)

        memory_ctx = self._retriever.query_for_url(url, goal)
        known_site_profile = match_profile(url)
        target.site_profile.domain = urlparse(url).netloc
        if known_site_profile:
            target.site_profile.difficulty_hint = known_site_profile.difficulty
            target.site_profile.extraction_hints = list(known_site_profile.analysis_hints)
            target.site_profile.notes = [
                f"category={known_site_profile.category}",
                f"strategy={known_site_profile.strategy}",
            ]

        target.interaction_goal = _build_enriched_goal(target, goal, runtime_policy, known_site_profile)
        plan_decision = self._planner.build(target, budget_usd=budget_usd, memory_ctx=memory_ctx)
        target.execution_plan = plan_decision.plan
        state.execution_plan = target.execution_plan.model_dump(mode="json")
        result.execution_plan = target.execution_plan
        result.output_dir = output_dir

        target.trace = workflow.checkpoint(
            sid,
            target.trace,
            "planning",
            "completed",
            summary=f"tier={target.execution_plan.tier.value} cost={target.execution_plan.estimated_cost}",
        )
        state.workflow_status = "running"
        self._store.save(state)

        return MasterRunContext(
            sid=sid,
            mode_name=mode_name,
            mode=mode,
            cost=cost,
            budget=budget,
            governor=governor,
            result=result,
            state=state,
            workflow=workflow,
            target=target,
            runtime_policy=runtime_policy,
            session_dir=session_dir,
            output_dir=output_dir,
            memory_ctx=memory_ctx,
            adapter_candidate=getattr(plan_decision, "adapter", None),
        )

    async def _finalize_run(self, ctx: MasterRunContext, completed: bool) -> MasterResult:
        ctx.result.analysis = ctx.analysis
        ctx.result.generated = ctx.generated
        ctx.result.verified = ctx.verified
        ctx.result.cost = ctx.cost
        ctx.result.execution_plan = ctx.target.execution_plan
        ctx.result.completed = completed and ctx.result.error is None

        ctx.state.completed = ctx.result.completed
        ctx.state.error = ctx.result.error
        ctx.state.workflow_status = "completed" if ctx.result.completed else ctx.state.workflow_status
        ctx.state.last_updated = datetime.now()
        self._store.save(ctx.state)

        if ctx.generated and ctx.generated.crawler_script_path:
            ctx.result.output_dir = ctx.generated.crawler_script_path.parent

        report_path = write_run_report(
            ctx.session_dir / "run_report.json",
            session_id=ctx.sid,
            target=ctx.target,
            policy=ctx.runtime_policy,
            difficulty_level=ctx.result.difficulty.level if ctx.result.difficulty else None,
            verified=ctx.verified,
            completed=ctx.result.completed,
            total_cost_usd=ctx.cost.total_usd,
            total_tokens=ctx.cost.total_tokens,
            ai_calls=ctx.cost.ai_calls,
            browser_sessions=ctx.cost.browser_sessions,
            node_calls=ctx.cost.node_calls,
            analysis=ctx.analysis,
            generated=ctx.generated,
        )
        ctx.result.report_path = report_path
        return ctx.result

    async def _maybe_short_circuit(self, ctx: MasterRunContext) -> bool | None:
        if ctx.target.execution_plan.tier == ExecutionTier.MANUAL_REVIEW:
            ctx.analysis = AnalysisResult(session_id=ctx.sid, manual_review_required=True)
            ctx.state.workflow_status = "waiting_manual_review"
            ctx.state.manual_review_reason = "; ".join(ctx.target.execution_plan.reasons)
            self._store.save(ctx.state)
            ctx.target.trace = ctx.workflow.request_manual_review(
                ctx.sid,
                ctx.target.trace,
                "planning",
                summary=ctx.state.manual_review_reason or "Planner requested manual review",
            )
            ctx.result.error = "manual review required by execution plan"
            return False

        if ctx.target.execution_plan.tier != ExecutionTier.ADAPTER_REUSE or ctx.adapter_candidate is None:
            return None

        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "adapter_reuse",
            "running",
            summary=getattr(ctx.adapter_candidate, "registry_key", ""),
        )
        reused, reuse_verified = await self._reuse_adapter(
            sid=ctx.sid,
            target=ctx.target,
            adapter=ctx.adapter_candidate,
            output_dir=ctx.output_dir,
        )
        if reuse_verified:
            ctx.generated = reused
            ctx.verified = True
            ctx.result.output_dir = ctx.output_dir
            ctx.result.adapter_reused = True
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "adapter_reuse",
                "completed",
                summary="Verified adapter reused successfully",
                artifacts=_artifact_map(
                    {
                        key: path
                        for key, path in {
                            "crawler_script": reused.crawler_script_path,
                            "bridge_server": reused.bridge_server_path,
                            "manifest": reused.manifest_path,
                            "session_state": reused.session_state_path,
                        }.items()
                        if path is not None
                    }
                ),
            )
            return True

        ctx.target.execution_plan = _escalate_execution_plan(
            ctx.target.execution_plan,
            "Adapter reuse failed verification; escalating to full pipeline.",
        )
        ctx.state.execution_plan = ctx.target.execution_plan.model_dump(mode="json")
        self._store.save(ctx.state)
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "adapter_reuse",
            "failed",
            summary="Adapter verification failed, escalated to full pipeline",
        )
        return None

    async def _run_discovery_stages(
        self,
        ctx: MasterRunContext,
        *,
        runner: NodeRunner,
        ast_analyzer: ASTAnalyzer,
    ) -> bool:
        crawl_stage = CrawlStage()
        fetch_stage = FetchStage()
        deob_stage = DeobfuscateStage(runner)
        static_stage = StaticAnalysisStage(ast_analyzer)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s1_crawl", "running")
        ctx.state.current_stage_index = 0
        self._store.save(ctx.state)
        crawl_result = await crawl_stage.execute(ctx.state, ctx.mode, target=ctx.target)
        if not crawl_result.success:
            ctx.result.error = crawl_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s1_crawl",
                "failed",
                summary=ctx.result.error or "",
            )
            return False
        ctx.target = crawl_result.next_input.get("target", ctx.target)
        ctx.cost.add_browser_session()
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s1_crawl",
            "completed",
            summary=crawl_result.summary,
            artifacts=_artifact_map(crawl_result.artifacts),
        )

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s2_fetch", "running")
        ctx.state.current_stage_index = 1
        self._store.save(ctx.state)
        fetch_result = await fetch_stage.execute(ctx.state, ctx.mode, target=ctx.target)
        if not fetch_result.success:
            ctx.result.error = fetch_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s2_fetch",
                "failed",
                summary=ctx.result.error or "",
            )
            return False
        bundles = fetch_result.next_input.get("bundles", [])
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s2_fetch",
            "completed",
            summary=fetch_result.summary,
            artifacts=_artifact_map(fetch_result.artifacts),
        )

        bundles, cached_static = await self._check_bundle_cache(bundles)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s3_deobfuscate", "running")
        ctx.state.current_stage_index = 2
        self._store.save(ctx.state)
        deob_result = await deob_stage.execute(ctx.state, ctx.mode, bundles=bundles)
        if not deob_result.success:
            ctx.result.error = deob_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s3_deobfuscate",
                "failed",
                summary=ctx.result.error or "",
            )
            return False
        bundles = deob_result.next_input.get("bundles", bundles)
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s3_deobfuscate",
            "completed",
            summary=deob_result.summary,
            artifacts=_artifact_map(deob_result.artifacts),
        )

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s4_static", "running")
        ctx.state.current_stage_index = 3
        self._store.save(ctx.state)
        static_result = await static_stage.execute(ctx.state, ctx.mode, bundles=bundles)
        if not static_result.success:
            ctx.result.error = static_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s4_static",
                "failed",
                summary=ctx.result.error or "",
            )
            return False
        ctx.static_results = {
            **cached_static,
            **static_result.next_input.get("static_results", {}),
        }
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s4_static",
            "completed",
            summary=static_result.summary,
            artifacts=_artifact_map(static_result.artifacts),
        )
        return True

    async def _run_analysis_stages(self, ctx: MasterRunContext) -> bool:
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
                return False
            ctx.state.workflow_status = "running"
            ctx.state.manual_review_reason = ""
            self._store.save(ctx.state)

        if ctx.difficulty.recommended_path in ("static+dynamic", "full+human") and ctx.governor.allow_dynamic(
            ctx.cost,
            ctx.target.execution_plan,
        ):
            dyn_stage = DynamicAnalysisStage()
            ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s5_dynamic", "running")
            ctx.state.current_stage_index = 4
            self._store.save(ctx.state)
            dyn_result = await dyn_stage.execute(ctx.state, ctx.mode, target=ctx.target, static_results=ctx.static_results)
            if not dyn_result.success:
                ctx.result.error = dyn_result.error
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s5_dynamic",
                    "failed",
                    summary=ctx.result.error or "",
                )
                return False
            ctx.dynamic = dyn_result.next_input.get("dynamic")
            ctx.cost.add_browser_session()
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s5_dynamic",
                "completed",
                summary=dyn_result.summary,
                artifacts=_artifact_map(dyn_result.artifacts),
            )

        ctx.analysis = AnalysisResult(session_id=ctx.sid, static=ctx.static_results, dynamic=ctx.dynamic)

        if not ctx.governor.allow_ai(ctx.cost, ctx.target.execution_plan):
            ctx.result.error = "budget exhausted before AI analysis"
            return False

        ctx.ai_client = AIClient(api_key=settings.anthropic_api_key, model=settings.model)
        ai_stage = AIAnalysisStage(ctx.ai_client, ctx.cost, ctx.budget, self._retriever)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s6_ai_analyze", "running")
        ctx.state.current_stage_index = 5
        self._store.save(ctx.state)
        ai_result = await ai_stage.execute(
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
            return False

        ctx.analysis = ai_result.next_input.get("analysis", ctx.analysis)
        ctx.hypothesis = ai_result.next_input.get("hypothesis")
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s6_ai_analyze",
            "completed",
            summary=ai_result.summary,
            artifacts=_artifact_map(ai_result.artifacts),
        )

        if ctx.analysis is None or ctx.hypothesis is None:
            ctx.result.error = "AI analysis did not produce a usable hypothesis"
            return False

        if not ctx.analysis.ready_for_codegen and ctx.mode_name != "auto":
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
                return False

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
            return False

        return True

    async def _run_codegen_and_verify(self, ctx: MasterRunContext) -> bool:
        if ctx.ai_client is None or ctx.analysis is None or ctx.hypothesis is None:
            ctx.result.error = "code generation prerequisites are missing"
            return False

        codegen_stage = CodeGenStage(ctx.ai_client, ctx.cost, ctx.budget, self._retriever)
        verify_stage = VerifyStage(ctx.ai_client, ctx.cost, ctx.budget)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s7_codegen", "running")
        ctx.state.current_stage_index = 6
        self._store.save(ctx.state)
        codegen_result = await codegen_stage.execute(
            ctx.state,
            ctx.mode,
            hypothesis=ctx.hypothesis,
            static_results=ctx.static_results,
            target=ctx.target,
            dynamic=ctx.dynamic,
        )
        if not codegen_result.success:
            ctx.result.error = codegen_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s7_codegen",
                "failed",
                summary=ctx.result.error or "",
            )
            return False

        ctx.generated = codegen_result.next_input.get("generated")
        if ctx.generated is None:
            ctx.result.error = "code generation did not return crawler artifacts"
            return False

        ctx.result.output_dir = ctx.output_dir
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s7_codegen",
            "completed",
            summary=codegen_result.summary,
            artifacts=_artifact_map(codegen_result.artifacts),
        )

        ctx.target.compliance.stability_runs = ctx.governor.stability_runs(ctx.target, ctx.target.execution_plan)
        max_verify_retries = max(1, ctx.target.compliance.max_auto_verify_retries)
        for attempt in range(max_verify_retries):
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s8_verify",
                "running",
                summary=f"attempt {attempt + 1}/{max_verify_retries}",
            )
            ctx.state.current_stage_index = 7
            self._store.save(ctx.state)
            verify_result = await verify_stage.execute(
                ctx.state,
                ctx.mode,
                generated=ctx.generated,
                target=ctx.target,
                hypothesis=ctx.hypothesis,
                live_verify=ctx.target.compliance.allow_live_verification,
            )
            if not verify_result.success:
                ctx.result.error = verify_result.error
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s8_verify",
                    "failed",
                    summary=ctx.result.error or "",
                )
                return False

            ctx.generated = verify_result.next_input.get("generated", ctx.generated)
            verification = verify_result.next_input.get("verification")
            verification_analysis = verify_result.next_input.get("verification_analysis")
            ctx.verified = ctx.generated.verified
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s8_verify",
                "completed" if ctx.verified else "failed",
                summary=verify_result.summary,
                artifacts=_artifact_map(verify_result.artifacts),
            )
            if ctx.verified:
                break
            if verification_analysis and verification_analysis.retry_strategy == "switch_to_bridge":
                ctx.hypothesis.codegen_strategy = "js_bridge"
                ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
                ctx.analysis.ai_hypothesis = ctx.hypothesis
                ctx.analysis.signature_spec = ctx.hypothesis.signature_spec
                ctx.analysis.overall_confidence = ctx.hypothesis.confidence
                ctx.analysis.ready_for_codegen = (
                    ctx.hypothesis.confidence > 0.5
                    and ctx.hypothesis.signature_spec.codegen_strategy != "manual_required"
                )
                ctx.analysis.manual_review_required = ctx.hypothesis.signature_spec.codegen_strategy == "manual_required"

                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "running",
                    summary="retry with js_bridge",
                )
                ctx.state.current_stage_index = 6
                self._store.save(ctx.state)
                codegen_result = await codegen_stage.execute(
                    ctx.state,
                    ctx.mode,
                    hypothesis=ctx.hypothesis,
                    static_results=ctx.static_results,
                    target=ctx.target,
                    dynamic=ctx.dynamic,
                )
                if not codegen_result.success:
                    ctx.result.error = codegen_result.error
                    ctx.target.trace = ctx.workflow.checkpoint(
                        ctx.sid,
                        ctx.target.trace,
                        "s7_codegen",
                        "failed",
                        summary=ctx.result.error or "",
                    )
                    return False
                ctx.generated = codegen_result.next_input.get("generated", ctx.generated)
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "completed",
                    summary=f"{codegen_result.summary} (retry)",
                    artifacts=_artifact_map(codegen_result.artifacts),
                )
                continue
            if verification_analysis and verification_analysis.retry_strategy == "give_up":
                break
            if verification is not None and not verification.retry_reason:
                break

        ctx.generated.verified = ctx.verified
        if ctx.verified and ctx.target.execution_plan.should_persist_adapter:
            self._adapter_registry.register(ctx.target, ctx.generated, ctx.analysis, verified=True)
        return True

    async def _write_memory(self, ctx: MasterRunContext) -> None:
        if ctx.ai_client is None or ctx.analysis is None:
            return
        mem_agent = MemoryWriterAgent(ctx.ai_client, ctx.cost, ctx.budget, writer=self._mem_writer)
        await mem_agent.write(
            session_id=ctx.sid,
            target=ctx.target,
            analysis=ctx.analysis,
            hypothesis=ctx.analysis.ai_hypothesis if ctx.analysis else None,
            cost=ctx.cost,
            verified=ctx.verified,
        )
        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "memory_write", "completed", summary="Memory updated")
        ctx.state.current_stage_index = 8
        self._store.save(ctx.state)

    async def _check_bundle_cache(self, bundles):
        uncached = []
        cached_static: dict[str, StaticAnalysis] = {}
        for bundle in bundles:
            cached = self._db.get_bundle_cache(bundle.content_hash)
            if cached and cached.analysis_json:
                try:
                    static = StaticAnalysis.model_validate_json(cached.analysis_json)
                    cached_static[bundle.bundle_id] = static
                    log.info("static_cache_hit", bundle_id=bundle.bundle_id)
                    continue
                except ValueError:
                    log.exception("static_cache_invalid", bundle_id=bundle.bundle_id)
            uncached.append(bundle)
        return uncached, cached_static

    async def _reuse_adapter(
        self,
        *,
        sid: str,
        target: TargetSite,
        adapter,
        output_dir: Path,
    ) -> tuple[GeneratedCode, bool]:
        materialized = self._adapter_registry.materialize(adapter, output_dir)
        if materialized.session_state_path:
            target.session_state.storage_state_path = str(materialized.session_state_path)

        generated = GeneratedCode(
            session_id=sid,
            output_mode=adapter.output_mode,
            crawler_script_path=materialized.crawler_script_path,
            bridge_server_path=materialized.bridge_server_path,
            manifest_path=materialized.manifest_path,
            session_state_path=materialized.session_state_path,
            verified=False,
            verification_notes="adapter registry reuse candidate",
        )

        verifier = VerificationEngine()
        verification = await verifier.verify(
            generated,
            target,
            live_verify=target.compliance.allow_live_verification,
        )
        generated.verified = verification.ok
        generated.verification_notes = verification.report
        return generated, verification.ok


def _build_enriched_goal(target: TargetSite, goal: str, runtime_policy, known_site_profile) -> str:
    login_context = "unknown"
    if target.requires_login is True:
        login_context = "authenticated session required"
    elif target.requires_login is False:
        login_context = "anonymous access expected"

    context_parts = [
        f"known endpoint: {target.known_endpoint or 'discover automatically'}",
        f"antibot: {target.antibot_type}",
        f"login: {login_context}",
        f"output format: {target.output_format}",
        f"crawl rate: {target.crawl_rate}",
        f"runtime wait: {runtime_policy.goto_wait_until}/{runtime_policy.post_navigation_wait_ms}ms",
    ]
    enriched = f"{goal}\n\n[user context] " + " | ".join(context_parts)
    if known_site_profile:
        enriched += (
            f"\n[known profile] category={known_site_profile.category}, "
            f"algorithm={known_site_profile.typical_algorithm}, signals={known_site_profile.key_signals[:3]}"
        )
    return enriched


def _artifact_map(artifacts: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in artifacts.items()}


def _escalate_execution_plan(plan: ExecutionPlan, reason: str) -> ExecutionPlan:
    escalated = plan.model_copy(deep=True)
    escalated.tier = ExecutionTier.BROWSER_FULL
    escalated.adapter_hit = False
    escalated.adapter_key = ""
    escalated.requires_browser = True
    escalated.requires_dynamic_analysis = True
    escalated.requires_ai = True
    escalated.skip_fetch_and_static = False
    escalated.skip_codegen = False
    escalated.should_persist_adapter = True
    escalated.enable_trace_capture = True
    escalated.enable_action_flow = True
    escalated.enable_target_confirmation = True
    escalated.max_crawl_retries = max(2, escalated.max_crawl_retries)
    escalated.max_session_rotations = max(2, escalated.max_session_rotations)
    escalated.verification_mode = VerificationMode.STANDARD
    escalated.reasons.append(reason)
    return escalated
