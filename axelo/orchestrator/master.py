from __future__ import annotations

import time
import uuid
from datetime import datetime
from urllib.parse import urlparse

import structlog

from axelo.analysis import ASTAnalyzer
from axelo.app.flows import AnalysisFlow, DeliveryFlow, DiscoveryFlow, ReuseFlow
from axelo.classifier.rules import DifficultyScore
from axelo.config import settings
from axelo.cost import CostBudget, CostGovernor, CostRecord
from axelo.domain.services import (
    AnalysisRoutingService,
    PlanningService,
    VerificationPolicyService,
)
from axelo.js_tools.runner import NodeRunner
from axelo.memory.db import MemoryDB
from axelo.memory.retriever import MemoryRetriever
from axelo.memory.vector_store import VectorStore
from axelo.memory.writer import MemoryWriter
from axelo.models.execution import ExecutionPlan
from axelo.models.pipeline import PipelineState
from axelo.models.target import BrowserProfile, TargetSite
from axelo.modes.registry import create_mode
from axelo.orchestrator.runtime import MasterResult, MasterRunContext
from axelo.orchestrator.workflow_runtime import WorkflowRuntime
from axelo.patterns.common import match_profile
from axelo.planner import Planner
from axelo.policies import resolve_runtime_policy
from axelo.storage import AdapterRegistry, AnalysisCache, SessionStore, WorkflowStore
from axelo.telemetry import write_run_report

log = structlog.get_logger()


class MasterOrchestrator:
    """Primary orchestrator for the current Axelo runtime."""

    def __init__(self) -> None:
        self._store = SessionStore(settings.sessions_dir)
        self._workflow_store = WorkflowStore(settings.sessions_dir)
        self._adapter_registry = AdapterRegistry(settings.workspace)
        self._analysis_cache = AnalysisCache(settings.workspace)
        mem_dir = settings.workspace / "memory"
        self._db = MemoryDB(mem_dir / "axelo.db")
        self._vs = VectorStore(mem_dir / "vectors")
        self._retriever = MemoryRetriever(self._db, self._vs)
        self._mem_writer = MemoryWriter(self._db, self._vs)

        self._planning = PlanningService(Planner(self._adapter_registry))
        self._analysis_routing = AnalysisRoutingService()
        self._verification_policy = VerificationPolicyService()

        self._reuse_flow = ReuseFlow(
            store=self._store,
            workflow_store=self._workflow_store,
            adapter_registry=self._adapter_registry,
        )
        self._discovery_flow = DiscoveryFlow(
            store=self._store,
            analysis_cache=self._analysis_cache,
            db=self._db,
            routing_service=self._analysis_routing,
        )
        self._analysis_flow = AnalysisFlow(
            store=self._store,
            db=self._db,
            retriever=self._retriever,
            analysis_cache=self._analysis_cache,
            routing_service=self._analysis_routing,
        )
        self._delivery_flow = DeliveryFlow(
            store=self._store,
            adapter_registry=self._adapter_registry,
            retriever=self._retriever,
            mem_writer=self._mem_writer,
            verification_policy=self._verification_policy,
        )

    async def run(
        self,
        url: str,
        goal: str,
        target_hint: str = "",
        use_case: str = "research",
        authorization_status: str = "pending",
        replay_mode: str = "discover_only",
        mode_name: str = "interactive",
        session_id: str | None = None,
        budget_usd: float = 2.0,
        resume: bool = False,
        known_endpoint: str = "",
        antibot_type: str = "unknown",
        requires_login: bool | None = None,
        output_format: str = "print",
        crawl_rate: str = "standard",
        crawl_item_limit: int = 100,
        crawl_page_limit: int | None = None,
        browser_profile: BrowserProfile | None = None,
    ) -> MasterResult:
        ctx = await self._initialize_run_context(
            url=url,
            goal=goal,
            target_hint=target_hint,
            use_case=use_case,
            authorization_status=authorization_status,
            replay_mode=replay_mode,
            mode_name=mode_name,
            session_id=session_id,
            budget_usd=budget_usd,
            resume=resume,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
            crawl_item_limit=crawl_item_limit,
            crawl_page_limit=crawl_page_limit,
            browser_profile=browser_profile,
        )

        short_circuit = await self._reuse_flow.run(ctx)
        if short_circuit is not None:
            return await self._finalize_run(ctx, short_circuit)

        runner = NodeRunner(settings.node_bin)
        await runner.start()
        ctx.cost.add_node_call(stage="node_runtime")

        try:
            ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "master", "started", summary="Run started")
            ctx.state.workflow_status = "running"
            self._store.save(ctx.state)

            ast_analyzer = ASTAnalyzer(runner)
            discovery = await self._discovery_flow.run(ctx, runner=runner, ast_analyzer=ast_analyzer)
            if discovery is None:
                return await self._finalize_run(ctx, False)

            analysis = await self._analysis_flow.run(ctx)
            if analysis is None:
                return await self._finalize_run(ctx, False)

            delivery = await self._delivery_flow.run(ctx)
            if delivery is None:
                return await self._finalize_run(ctx, False)
        except Exception as exc:
            ctx.result.error = str(exc)
            ctx.state.workflow_status = "failed"
            ctx.state.error = ctx.result.error
            self._store.save(ctx.state)
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "master",
                "failed",
                summary=ctx.result.error,
            )
            return await self._finalize_run(ctx, False)
        finally:
            await runner.stop()

        return await self._finalize_run(ctx, True)

    async def _initialize_run_context(
        self,
        *,
        url: str,
        goal: str,
        target_hint: str,
        use_case: str,
        authorization_status: str,
        replay_mode: str,
        mode_name: str,
        session_id: str | None,
        budget_usd: float,
        resume: bool,
        known_endpoint: str,
        antibot_type: str,
        requires_login: bool | None,
        output_format: str,
        crawl_rate: str,
        crawl_item_limit: int,
        crawl_page_limit: int | None,
        browser_profile: BrowserProfile | None,
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
            target_hint=target_hint,
            use_case=use_case,
            authorization_status=authorization_status,
            replay_mode=replay_mode,
            browser_profile=browser_profile.model_copy(deep=True) if browser_profile else BrowserProfile(),
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
            crawl_item_limit=crawl_item_limit,
            crawl_page_limit=crawl_page_limit,
            trace=trace,
        )
        runtime_policy = resolve_runtime_policy(target)
        target.browser_profile = runtime_policy.apply_to_profile(target.browser_profile)
        target.compliance.allow_live_verification = (
            target.authorization_status == "authorized" and target.replay_mode == "authorized_replay"
        )
        if not target.compliance.allow_live_verification:
            target.compliance.notes.append("Live verification disabled by authorization/replay mode.")

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
        planning_started = time.monotonic()
        plan_decision = self._planning.build(target, budget_usd=budget_usd, memory_ctx=memory_ctx)
        target.execution_plan = plan_decision.plan
        cost.set_route(target.execution_plan.route_label)
        if target.execution_plan.adapter_hit:
            cost.add_reuse_hit("adapter")
        state.execution_plan = target.execution_plan.model_dump(mode="json")
        result.execution_plan = target.execution_plan
        result.output_dir = output_dir
        result.route_label = target.execution_plan.route_label
        cost.set_stage_timing(
            "planning",
            int((time.monotonic() - planning_started) * 1000),
            status="completed",
            exit_reason=target.execution_plan.route_label,
        )

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
        ctx.result.route_label = ctx.cost.route_label
        ctx.result.reuse_hits = list(ctx.cost.reuse_hits)
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
            route_label=ctx.cost.route_label,
            reuse_hits=ctx.cost.reuse_hits,
            stage_costs=ctx.cost.stage_costs(),
            cost_strategy=ctx.target.execution_plan.cost_strategy if ctx.target.execution_plan else "balanced",
            analysis=ctx.analysis,
            generated=ctx.generated,
        )
        ctx.result.report_path = report_path
        return ctx.result


def _build_enriched_goal(target: TargetSite, goal: str, runtime_policy, known_site_profile) -> str:
    login_context = "unknown"
    if target.requires_login is True:
        login_context = "authenticated session required"
    elif target.requires_login is False:
        login_context = "anonymous access expected"

    normalized_goal = goal.strip()
    if target.target_hint:
        normalized_goal = f"{normalized_goal}\n\n[target object] {target.target_hint}"

    context_parts = [
        f"use case: {target.use_case}",
        f"authorization: {target.authorization_status}",
        f"replay mode: {target.replay_mode}",
        f"known endpoint: {target.known_endpoint or 'discover automatically'}",
        f"target hint: {target.target_hint or 'not provided'}",
        f"antibot: {target.antibot_type}",
        f"login: {login_context}",
        f"output format: {target.output_format}",
        f"crawl rate: {target.crawl_rate}",
        f"crawl item limit: {target.crawl_item_limit}",
        f"crawl page limit: {target.crawl_page_limit if target.crawl_page_limit is not None else 'auto'}",
        f"runtime wait: {runtime_policy.goto_wait_until}/{runtime_policy.post_navigation_wait_ms}ms",
    ]
    enriched = f"{normalized_goal}\n\n[user context] " + " | ".join(context_parts)
    if known_site_profile:
        enriched += (
            f"\n[known profile] category={known_site_profile.category}, "
            f"algorithm={known_site_profile.typical_algorithm}, signals={known_site_profile.key_signals[:3]}"
        )
    return enriched


__all__ = ["MasterOrchestrator", "MasterResult"]
