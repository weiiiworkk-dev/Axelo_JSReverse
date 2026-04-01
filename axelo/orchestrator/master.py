from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import structlog

from axelo.agents.codegen_agent import CodeGenAgent
from axelo.agents.hypothesis import HypothesisAgent
from axelo.agents.memory_writer_agent import MemoryWriterAgent
from axelo.agents.scanner import ScannerAgent
from axelo.agents.verifier_agent import VerifierAgent
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
from axelo.models.analysis import AnalysisResult, DynamicAnalysis, StaticAnalysis
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

from axelo.pipeline.stages import CrawlStage, DeobfuscateStage, DynamicAnalysisStage, FetchStage, StaticAnalysisStage

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
        sid = session_id or str(uuid.uuid4())[:8]
        mode = create_mode(mode_name)
        cost = CostRecord(session_id=sid)
        budget = CostBudget(max_usd=budget_usd)
        governor = CostGovernor(max_usd=budget_usd)
        result = MasterResult(session_id=sid, url=url)
        analysis: AnalysisResult | None = None
        generated: GeneratedCode | None = None
        verified = False

        session_dir = settings.session_dir(sid)
        session_dir.mkdir(parents=True, exist_ok=True)

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
            target.site_profile.domain = urlparse(url).netloc
            target.site_profile.difficulty_hint = known_site_profile.difficulty
            target.site_profile.extraction_hints = list(known_site_profile.analysis_hints)
            target.site_profile.notes = [f"category={known_site_profile.category}", f"strategy={known_site_profile.strategy}"]

        target.interaction_goal = _build_enriched_goal(target, goal, runtime_policy, known_site_profile)
        result.output_dir = session_dir / "output"
        plan_decision = self._planner.build(target, budget_usd=budget_usd, memory_ctx=memory_ctx)
        target.execution_plan = plan_decision.plan
        state.execution_plan = target.execution_plan.model_dump(mode="json")
        result.execution_plan = target.execution_plan

        async def finalize(completed: bool) -> MasterResult:
            result.analysis = analysis
            result.generated = generated
            result.verified = verified
            result.cost = cost
            result.execution_plan = target.execution_plan
            result.completed = completed and result.error is None
            state.completed = result.completed
            state.error = result.error
            state.workflow_status = "completed" if result.completed else state.workflow_status
            state.last_updated = __import__("datetime").datetime.now()
            self._store.save(state)
            if result.generated:
                result.output_dir = result.generated.crawler_script_path.parent if result.generated.crawler_script_path else result.output_dir
            report_path = write_run_report(
                session_dir / "run_report.json",
                session_id=sid,
                target=target,
                policy=runtime_policy,
                difficulty_level=result.difficulty.level if result.difficulty else None,
                verified=verified,
                completed=result.completed,
                total_cost_usd=cost.total_usd,
                total_tokens=cost.total_tokens,
                ai_calls=cost.ai_calls,
                browser_sessions=cost.browser_sessions,
                node_calls=cost.node_calls,
                analysis=analysis,
                generated=generated,
            )
            result.report_path = report_path
            return result

        target.trace = workflow.checkpoint(
            sid,
            target.trace,
            "planning",
            "completed",
            summary=f"tier={target.execution_plan.tier.value} cost={target.execution_plan.estimated_cost}",
        )
        state.workflow_status = "running"
        self._store.save(state)

        if target.execution_plan.tier == ExecutionTier.MANUAL_REVIEW:
            analysis = AnalysisResult(session_id=sid, manual_review_required=True)
            state.workflow_status = "waiting_manual_review"
            state.manual_review_reason = "; ".join(target.execution_plan.reasons)
            self._store.save(state)
            target.trace = workflow.request_manual_review(
                sid,
                target.trace,
                "planning",
                summary=state.manual_review_reason or "Planner requested manual review",
            )
            result.error = "manual review required by execution plan"
            return await finalize(False)

        output_dir = session_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        if target.execution_plan.tier == ExecutionTier.ADAPTER_REUSE and plan_decision.adapter is not None:
            target.trace = workflow.checkpoint(sid, target.trace, "adapter_reuse", "running", summary=plan_decision.adapter.registry_key)
            reused, reuse_verified = await self._reuse_adapter(
                sid=sid,
                target=target,
                adapter=plan_decision.adapter,
                output_dir=output_dir,
            )
            if reuse_verified:
                generated = reused
                verified = True
                result.generated = generated
                result.output_dir = output_dir
                result.adapter_reused = True
                target.trace = workflow.checkpoint(
                    sid,
                    target.trace,
                    "adapter_reuse",
                    "completed",
                    summary="Verified adapter reused successfully",
                    artifacts=_artifact_map(
                        {
                            key: path
                            for key, path in {
                                "crawler_script": generated.crawler_script_path,
                                "bridge_server": generated.bridge_server_path,
                                "manifest": generated.manifest_path,
                                "session_state": generated.session_state_path,
                            }.items()
                            if path is not None
                        }
                    ),
                )
                return await finalize(True)

            target.execution_plan = _escalate_execution_plan(target.execution_plan, "Adapter reuse failed verification; escalating to full pipeline.")
            state.execution_plan = target.execution_plan.model_dump(mode="json")
            self._store.save(state)
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "adapter_reuse",
                "failed",
                summary="Adapter verification failed, escalated to full pipeline",
            )

        runner = NodeRunner(settings.node_bin)
        await runner.start()
        cost.add_node_call()

        try:
            ai_client = AIClient(api_key=settings.anthropic_api_key, model=settings.model)
            ast_analyzer = ASTAnalyzer(runner)

            crawl_stage = CrawlStage()
            fetch_stage = FetchStage()
            deob_stage = DeobfuscateStage(runner)
            static_stage = StaticAnalysisStage(ast_analyzer)

            target.trace = workflow.checkpoint(sid, target.trace, "master", "started", summary="Run started")
            state.workflow_status = "running"
            self._store.save(state)

            target.trace = workflow.checkpoint(sid, target.trace, "s1_crawl", "running")
            state.current_stage_index = 0
            self._store.save(state)
            crawl_result = await crawl_stage.execute(state, mode, target=target)
            if not crawl_result.success:
                result.error = crawl_result.error
                target.trace = workflow.checkpoint(sid, target.trace, "s1_crawl", "failed", summary=result.error or "")
                return await finalize(False)
            target = crawl_result.next_input.get("target", target)
            cost.add_browser_session()
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "s1_crawl",
                "completed",
                summary=crawl_result.summary,
                artifacts=_artifact_map(crawl_result.artifacts),
            )

            target.trace = workflow.checkpoint(sid, target.trace, "s2_fetch", "running")
            state.current_stage_index = 1
            self._store.save(state)
            fetch_result = await fetch_stage.execute(state, mode, target=target)
            if not fetch_result.success:
                result.error = fetch_result.error
                target.trace = workflow.checkpoint(sid, target.trace, "s2_fetch", "failed", summary=result.error or "")
                return await finalize(False)
            bundles = fetch_result.next_input.get("bundles", [])
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "s2_fetch",
                "completed",
                summary=fetch_result.summary,
                artifacts=_artifact_map(fetch_result.artifacts),
            )

            bundles, cached_static = await self._check_bundle_cache(bundles)

            target.trace = workflow.checkpoint(sid, target.trace, "s3_deobfuscate", "running")
            state.current_stage_index = 2
            self._store.save(state)
            deob_result = await deob_stage.execute(state, mode, bundles=bundles)
            if not deob_result.success:
                result.error = deob_result.error
                target.trace = workflow.checkpoint(sid, target.trace, "s3_deobfuscate", "failed", summary=result.error or "")
                return await finalize(False)
            bundles = deob_result.next_input.get("bundles", bundles)
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "s3_deobfuscate",
                "completed",
                summary=deob_result.summary,
                artifacts=_artifact_map(deob_result.artifacts),
            )

            target.trace = workflow.checkpoint(sid, target.trace, "s4_static", "running")
            state.current_stage_index = 3
            self._store.save(state)
            static_result = await static_stage.execute(state, mode, bundles=bundles)
            if not static_result.success:
                result.error = static_result.error
                target.trace = workflow.checkpoint(sid, target.trace, "s4_static", "failed", summary=result.error or "")
                return await finalize(False)
            static_results: dict[str, StaticAnalysis] = {
                **cached_static,
                **static_result.next_input.get("static_results", {}),
            }
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "s4_static",
                "completed",
                summary=static_result.summary,
                artifacts=_artifact_map(static_result.artifacts),
            )

            known_pattern = self._db.get_site_pattern(memory_ctx.get("domain", "")) if memory_ctx.get("known_pattern") else None
            difficulty = classify(target, static_results, known_pattern)
            result.difficulty = difficulty

            if difficulty.level == "extreme" and target.compliance.require_manual_for_extreme:
                analysis = AnalysisResult(session_id=sid, static=static_results, manual_review_required=True)
                state.workflow_status = "waiting_manual_review"
                state.manual_review_reason = "Extreme target requires manual review"
                self._store.save(state)
                target.trace = workflow.request_manual_review(
                    sid,
                    target.trace,
                    "difficulty",
                    summary=f"Extreme site classified: {difficulty.reasons}",
                )

                decision = Decision(
                    stage="difficulty",
                    decision_type=DecisionType.MANUAL_REVIEW,
                    prompt="Target classified as extreme. Manual review is required before continuing.",
                    options=["stop_for_manual_review", "force_continue"],
                    default="stop_for_manual_review",
                    context_summary=", ".join(difficulty.reasons),
                )
                outcome = await mode.gate(decision, state)
                if outcome != "force_continue":
                    result.error = "manual review required for extreme target"
                    return await finalize(False)
                state.workflow_status = "running"
                state.manual_review_reason = ""
                self._store.save(state)

            dynamic: DynamicAnalysis | None = None
            if difficulty.recommended_path in ("static+dynamic", "full+human") and governor.allow_dynamic(cost, target.execution_plan):
                target.trace = workflow.checkpoint(sid, target.trace, "s5_dynamic", "running")
                state.current_stage_index = 4
                self._store.save(state)
                dyn_stage = DynamicAnalysisStage()
                dyn_result = await dyn_stage.execute(state, mode, target=target, static_results=static_results)
                if not dyn_result.success:
                    result.error = dyn_result.error
                    target.trace = workflow.checkpoint(sid, target.trace, "s5_dynamic", "failed", summary=result.error or "")
                    return await finalize(False)
                dynamic = dyn_result.next_input.get("dynamic")
                cost.add_browser_session()
                target.trace = workflow.checkpoint(
                    sid,
                    target.trace,
                    "s5_dynamic",
                    "completed",
                    summary=dyn_result.summary,
                    artifacts=_artifact_map(dyn_result.artifacts),
                )

            analysis = AnalysisResult(session_id=sid, static=static_results, dynamic=dynamic)

            if not governor.allow_ai(cost, target.execution_plan):
                result.error = "budget exhausted before AI analysis"
                return await finalize(False)

            target.trace = workflow.checkpoint(sid, target.trace, "scanner", "running")
            state.current_stage_index = 5
            self._store.save(state)
            scanner = ScannerAgent(ai_client, cost, budget, retriever=self._retriever)
            scan_report = await scanner.scan(target, static_results)
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "scanner",
                "completed",
                summary=f"difficulty={scan_report.estimated_difficulty}",
            )

            target.trace = workflow.checkpoint(sid, target.trace, "hypothesis", "running")
            state.current_stage_index = 6
            self._store.save(state)
            hypothesis_agent = HypothesisAgent(ai_client, cost, budget, retriever=self._retriever)
            hypothesis = await hypothesis_agent.generate(target, static_results, dynamic, scan_report)
            signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)
            hypothesis.signature_spec = signature_spec
            analysis.ai_hypothesis = hypothesis
            analysis.signature_spec = signature_spec
            analysis.overall_confidence = hypothesis.confidence
            analysis.ready_for_codegen = hypothesis.confidence > 0.5 and signature_spec.codegen_strategy != "manual_required"
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "hypothesis",
                "completed",
                summary=f"confidence={hypothesis.confidence:.2f} strategy={signature_spec.codegen_strategy}",
            )

            if not analysis.ready_for_codegen and mode_name != "auto":
                decision = Decision(
                    stage="master",
                    decision_type=DecisionType.APPROVE_STAGE,
                    prompt=f"AI confidence is low ({hypothesis.confidence:.0%}). Continue with code generation?",
                    options=["continue", "stop"],
                    default="continue",
                )
                outcome = await mode.gate(decision, state)
                if outcome == "stop":
                    result.error = "user declined low-confidence result"
                    return await finalize(False)

            if signature_spec.codegen_strategy == "manual_required":
                result.error = "signature spec requires manual implementation"
                target.trace = workflow.request_manual_review(
                    sid,
                    target.trace,
                    "signature_spec",
                    summary="Structured analysis marked this target as manual_required",
                )
                return await finalize(False)

            output_dir = session_dir / "output"
            target.trace = workflow.checkpoint(sid, target.trace, "codegen", "running")
            state.current_stage_index = 7
            self._store.save(state)
            codegen = CodeGenAgent(ai_client, cost, budget, retriever=self._retriever)
            artifacts = await codegen.generate(target, hypothesis, static_results, dynamic, output_dir)
            generated = GeneratedCode(
                session_id=sid,
                output_mode="standalone" if not artifacts.get("bridge_server") else "bridge",
                crawler_script_path=artifacts.get("crawler_script"),
                crawler_deps=_read_requirements(artifacts.get("requirements")),
                bridge_server_path=artifacts.get("bridge_server"),
                manifest_path=artifacts.get("manifest"),
                session_state_path=Path(target.session_state.storage_state_path) if target.session_state.storage_state_path else None,
            )
            result.generated = generated
            result.output_dir = output_dir
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "codegen",
                "completed",
                summary=f"generated={list(artifacts.keys())}",
                artifacts=_artifact_map(artifacts),
            )

            target.trace = workflow.checkpoint(sid, target.trace, "verify", "running")
            state.current_stage_index = 8
            self._store.save(state)
            target.compliance.stability_runs = governor.stability_runs(target, target.execution_plan)
            verifier = VerifierAgent(ai_client, cost, budget)
            max_verify_retries = max(1, target.compliance.max_auto_verify_retries)
            for attempt in range(max_verify_retries):
                ver_result, ver_analysis = await verifier.verify_and_analyze(
                    generated,
                    target,
                    hypothesis,
                    live_verify=target.compliance.allow_live_verification,
                )
                verified = ver_result.ok
                generated.verification_notes = ver_result.report
                if verified:
                    break
                if ver_analysis and ver_analysis.retry_strategy == "switch_to_bridge":
                    hypothesis.codegen_strategy = "js_bridge"
                    hypothesis.signature_spec = build_signature_spec(target, hypothesis, static_results, dynamic)
                    artifacts = await codegen.generate(target, hypothesis, static_results, dynamic, output_dir)
                    generated.crawler_script_path = artifacts.get("crawler_script")
                    generated.bridge_server_path = artifacts.get("bridge_server")
                    generated.manifest_path = artifacts.get("manifest")
                elif ver_analysis and ver_analysis.retry_strategy == "give_up":
                    break

            generated.verified = verified
            target.trace = workflow.checkpoint(
                sid,
                target.trace,
                "verify",
                "completed" if verified else "failed",
                summary=generated.verification_notes[:300],
            )
            if verified and generated and target.execution_plan.should_persist_adapter:
                self._adapter_registry.register(target, generated, analysis, verified=True)

        except Exception as exc:
            result.error = str(exc)
            state.workflow_status = "failed"
            state.error = result.error
            self._store.save(state)
            target.trace = workflow.checkpoint(sid, target.trace, "master", "failed", summary=result.error)
            return await finalize(False)
        finally:
            await runner.stop()

        result.cost = cost
        mem_agent = MemoryWriterAgent(ai_client, cost, budget, writer=self._mem_writer)
        await mem_agent.write(
            session_id=sid,
            target=target,
            analysis=analysis,
            hypothesis=analysis.ai_hypothesis if analysis else None,
            cost=cost,
            verified=verified,
        )
        target.trace = workflow.checkpoint(sid, target.trace, "memory_write", "completed", summary="Memory updated")
        state.current_stage_index = 9
        self._store.save(state)
        return await finalize(True)

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
                except Exception:
                    pass
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


def _read_requirements(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            items.append(stripped)
    return items


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
