from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import structlog

from axelo.config import settings
from axelo.models.pipeline import PipelineState
from axelo.models.target import TargetSite, BrowserProfile
from axelo.models.analysis import AnalysisResult, StaticAnalysis, DynamicAnalysis
from axelo.models.codegen import GeneratedCode
from axelo.modes.base import ModeController
from axelo.modes.registry import create_mode
from axelo.storage.session_store import SessionStore
from axelo.cost.tracker import CostRecord, CostBudget
from axelo.memory.db import MemoryDB
from axelo.memory.vector_store import VectorStore
from axelo.memory.retriever import MemoryRetriever
from axelo.memory.writer import MemoryWriter
from axelo.classifier.rules import classify, DifficultyScore
from axelo.patterns.common import match_profile
from axelo.js_tools.runner import NodeRunner
from axelo.analysis.static.ast_analyzer import ASTAnalyzer
from axelo.ai.client import AIClient
from axelo.agents.scanner import ScannerAgent
from axelo.agents.hypothesis import HypothesisAgent
from axelo.agents.codegen_agent import CodeGenAgent
from axelo.agents.verifier_agent import VerifierAgent
from axelo.agents.memory_writer_agent import MemoryWriterAgent

# 各阶段 Stage
from axelo.pipeline.stages import (
    CrawlStage, FetchStage, DeobfuscateStage,
    StaticAnalysisStage, DynamicAnalysisStage,
)

log = structlog.get_logger()

MAX_VERIFY_RETRIES = 2


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
    error: str | None = None
    completed: bool = False


class MasterOrchestrator:
    """
    总控编排器。

    职责：
    1. 查记忆库 → 确认是否有已知模式
    2. 分流难度 → 选择执行路径（rules_only / static_only / static+dynamic / full+human）
    3. 按路径调度各阶段（数据采集 → 分析 → AI → 代码生成 → 验证）
    4. 控制成本（分层模型调用、预算守护）
    5. 失败时切换策略重试
    6. 写入记忆库
    """

    def __init__(self) -> None:
        # 基础设施
        self._store = SessionStore(settings.sessions_dir)
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
    ) -> MasterResult:
        sid = session_id or str(uuid.uuid4())[:8]
        mode = create_mode(mode_name)
        cost = CostRecord(session_id=sid)
        budget = CostBudget(max_usd=budget_usd)
        result = MasterResult(session_id=sid, url=url)

        # 确保工作目录存在
        session_dir = settings.session_dir(sid)
        session_dir.mkdir(parents=True, exist_ok=True)

        # 构建 PipelineState
        state = PipelineState(session_id=sid, mode=mode_name)
        if resume:
            loaded = self._store.load(sid)
            if loaded:
                state = loaded
                log.info("session_resumed", session_id=sid)

        # 构建目标
        target = TargetSite(
            url=url,
            session_id=sid,
            interaction_goal=goal,
            browser_profile=BrowserProfile(),
        )

        # 1. 查记忆库 + 匹配已知模式
        memory_ctx = self._retriever.query_for_url(url, goal)
        site_profile = match_profile(url)

        log.info(
            "master_start",
            session_id=sid,
            url=url,
            known_pattern=memory_ctx.get("known_pattern") is not None,
            site_profile=site_profile.category if site_profile else None,
        )

        # 给 AI 注入站点先验知识
        if site_profile:
            target.interaction_goal = (
                f"{goal}\n\n[先验知识] 该站点类型: {site_profile.category}，"
                f"典型算法: {site_profile.typical_algorithm}，"
                f"关键信号: {site_profile.key_signals[:3]}"
            )

        # 启动 Node.js 运行器
        runner = NodeRunner(settings.node_bin)
        await runner.start()
        cost.add_node_call()

        try:
            ai_client = AIClient(
                api_key=settings.anthropic_api_key,
                model=settings.model,
            )
            ast_analyzer = ASTAnalyzer(runner)

            # ── 阶段1-3：数据采集 ──────────────────────────────────
            crawl_stage = CrawlStage()
            fetch_stage = FetchStage()
            deob_stage = DeobfuscateStage(runner)

            crawl_result = await crawl_stage.execute(state, mode, target=target)
            if not crawl_result.success:
                result.error = crawl_result.error
                return result
            target = crawl_result.next_input.get("target", target)
            cost.add_browser_session()

            fetch_result = await fetch_stage.execute(state, mode, target=target)
            if not fetch_result.success:
                result.error = fetch_result.error
                return result
            bundles = fetch_result.next_input.get("bundles", [])

            # 检查 Bundle 缓存（静态分析结果可能已缓存）
            bundles, cached_static = await self._check_bundle_cache(bundles)

            deob_result = await deob_stage.execute(state, mode, bundles=bundles)
            bundles = deob_result.next_input.get("bundles", bundles)

            # ── 阶段4：静态分析 ────────────────────────────────────
            static_stage = StaticAnalysisStage(ast_analyzer)
            static_result = await static_stage.execute(state, mode, bundles=bundles)
            static_results: dict[str, StaticAnalysis] = {
                **cached_static,
                **static_result.next_input.get("static_results", {}),
            }

            # ── 难度分类 ───────────────────────────────────────────
            known_pattern = self._db.get_site_pattern(
                memory_ctx.get("domain", "")
            ) if memory_ctx.get("known_pattern") else None
            difficulty = classify(target, static_results, known_pattern)
            result.difficulty = difficulty

            log.info(
                "difficulty_classified",
                level=difficulty.level,
                score=difficulty.score,
                path=difficulty.recommended_path,
                reasons=difficulty.reasons[:2],
            )

            # ── 阶段5：动态分析（按难度决定是否执行）─────────────────
            dynamic: DynamicAnalysis | None = None

            needs_dynamic = (
                difficulty.recommended_path in ("static+dynamic", "full+human")
                and not budget.should_skip_dynamic(cost)
            )

            if needs_dynamic:
                dyn_stage = DynamicAnalysisStage()
                dyn_result = await dyn_stage.execute(
                    state, mode, target=target, static_results=static_results
                )
                dynamic = dyn_result.next_input.get("dynamic")
                cost.add_browser_session()

            analysis = AnalysisResult(
                session_id=sid,
                static=static_results,
                dynamic=dynamic,
            )
            result.analysis = analysis

            # ── AI 角色链：Scanner → Hypothesis ───────────────────
            if budget.should_skip_ai(cost):
                log.warning("budget_skip_ai")
                result.error = "预算不足，跳过AI分析"
                return result

            scanner = ScannerAgent(ai_client, cost, budget, retriever=self._retriever)
            scan_report = await scanner.scan(target, static_results)

            hypothesis_agent = HypothesisAgent(
                ai_client, cost, budget, retriever=self._retriever
            )
            hypothesis = await hypothesis_agent.generate(
                target, static_results, dynamic, scan_report
            )
            analysis.ai_hypothesis = hypothesis
            analysis.overall_confidence = hypothesis.confidence
            analysis.ready_for_codegen = hypothesis.confidence > 0.5

            # ── 人工决策点（non-auto 模式）─────────────────────────
            if not analysis.ready_for_codegen and mode_name != "auto":
                from axelo.models.pipeline import Decision, DecisionType
                decision = Decision(
                    stage="master",
                    decision_type=DecisionType.APPROVE_STAGE,
                    prompt=f"AI 置信度较低（{hypothesis.confidence:.0%}），是否继续生成代码？",
                    options=["继续生成", "放弃"],
                    default="继续生成",
                )
                outcome = await mode.gate(decision, state)
                if outcome == "放弃":
                    result.error = "用户放弃低置信度结果"
                    return result

            # ── 代码生成 ───────────────────────────────────────────
            output_dir = session_dir / "output"
            codegen = CodeGenAgent(ai_client, cost, budget, retriever=self._retriever)
            artifacts = await codegen.generate(
                target, hypothesis, static_results, dynamic, output_dir
            )

            generated = GeneratedCode(
                session_id=sid,
                output_mode="standalone" if "standalone_script" in artifacts else "bridge",
                standalone_script_path=artifacts.get("standalone_script"),
                bridge_client_path=artifacts.get("bridge_client"),
                bridge_server_path=artifacts.get("bridge_server"),
            )
            result.generated = generated
            result.output_dir = output_dir

            # ── 验证（含重试）─────────────────────────────────────
            verifier = VerifierAgent(ai_client, cost, budget)
            verified = False

            for attempt in range(MAX_VERIFY_RETRIES):
                ver_result, ver_analysis = await verifier.verify_and_analyze(
                    generated, target, hypothesis
                )
                verified = ver_result.ok

                if verified:
                    break

                if ver_analysis and ver_analysis.retry_strategy == "switch_to_bridge":
                    # 切换到桥接模式重新生成
                    log.info("retry_switch_bridge", attempt=attempt)
                    hypothesis.codegen_strategy = "js_bridge"
                    artifacts = await codegen.generate(
                        target, hypothesis, static_results, dynamic, output_dir
                    )
                    generated.bridge_client_path = artifacts.get("bridge_client")
                    generated.bridge_server_path = artifacts.get("bridge_server")
                elif ver_analysis and ver_analysis.retry_strategy == "give_up":
                    break

            generated.verified = verified
            result.verified = verified

        finally:
            await runner.stop()

        # ── 写入记忆库 ─────────────────────────────────────────────
        result.cost = cost
        mem_agent = MemoryWriterAgent(ai_client, cost, budget, writer=self._mem_writer)
        await mem_agent.write(
            session_id=sid,
            target=target,
            analysis=analysis,
            hypothesis=analysis.ai_hypothesis,
            cost=cost,
            verified=result.verified,
        )

        result.completed = True
        log.info(
            "master_done",
            session_id=sid,
            verified=verified,
            difficulty=difficulty.level,
            cost=cost.summary(),
        )
        return result

    async def _check_bundle_cache(self, bundles):
        """检查 bundle 静态分析缓存，返回 (未缓存bundles, 已缓存static_results)"""
        uncached = []
        cached_static: dict[str, StaticAnalysis] = {}

        for bundle in bundles:
            cached = self._db.get_bundle_cache(bundle.content_hash)
            if cached and cached.analysis_json:
                try:
                    sa = StaticAnalysis.model_validate_json(cached.analysis_json)
                    cached_static[bundle.bundle_id] = sa
                    log.info("static_cache_hit", bundle_id=bundle.bundle_id)
                    continue
                except Exception:
                    pass
            uncached.append(bundle)

        return uncached, cached_static
