from __future__ import annotations

import structlog

from axelo.analysis import ASTAnalyzer
from axelo.app.artifacts import DiscoveryArtifacts
from axelo.models.analysis import StaticAnalysis
from axelo.models.execution import ExecutionTier
from axelo.pipeline.stages import CrawlStage, DeobfuscateStage, FetchStage, StaticAnalysisStage

from ._common import artifact_map, bundle_hashes, execute_stage_with_metrics

log = structlog.get_logger()


class DiscoveryFlow:
    def __init__(self, *, store, analysis_cache, db, routing_service) -> None:
        self._store = store
        self._analysis_cache = analysis_cache
        self._db = db
        self._routing_service = routing_service

    async def run(self, ctx, *, runner, ast_analyzer: ASTAnalyzer) -> DiscoveryArtifacts | None:
        crawl_stage = CrawlStage()
        fetch_stage = FetchStage()
        deob_stage = DeobfuscateStage(runner)
        static_stage = StaticAnalysisStage(ast_analyzer)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s1_crawl", "running")
        ctx.state.current_stage_index = 0
        self._store.save(ctx.state)
        crawl_result = await execute_stage_with_metrics(
            ctx,
            crawl_stage,
            ctx.state,
            ctx.mode,
            target=ctx.target,
        )
        if not crawl_result.success:
            ctx.result.error = crawl_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s1_crawl",
                "failed",
                summary=ctx.result.error or "",
            )
            return None
        ctx.target = crawl_result.next_input.get("target", ctx.target)
        ctx.cost.add_browser_session(stage="s1_crawl")
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s1_crawl",
            "completed",
            summary=crawl_result.summary,
            artifacts=artifact_map(crawl_result.artifacts),
        )

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s2_fetch", "running")
        ctx.state.current_stage_index = 1
        self._store.save(ctx.state)
        fetch_result = await execute_stage_with_metrics(
            ctx,
            fetch_stage,
            ctx.state,
            ctx.mode,
            target=ctx.target,
            expand=False,
        )
        if not fetch_result.success:
            ctx.result.error = fetch_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s2_fetch",
                "failed",
                summary=ctx.result.error or "",
            )
            return None

        bundles = fetch_result.next_input.get("bundles", [])
        ctx.bundle_hashes = bundle_hashes(bundles)
        for bundle in bundles:
            ctx.cost.add_bundle_bytes(bundle.size_bytes, stage="s2_fetch")
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s2_fetch",
            "completed",
            summary=fetch_result.summary,
            artifacts=artifact_map(fetch_result.artifacts),
        )

        analysis_cache_entry = self._analysis_cache.lookup(ctx.target, ctx.bundle_hashes)
        if analysis_cache_entry is not None:
            ctx.analysis_cache_hit = True
            ctx.cost.add_reuse_hit("analysis_cache")
            ctx.static_results = analysis_cache_entry.static_models()
            ctx.cost.set_stage_timing("s3_deobfuscate", 0, status="skipped", exit_reason="analysis_cache_hit")
            ctx.cost.set_stage_timing("s4_static", 0, status="skipped", exit_reason="analysis_cache_hit")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s3_deobfuscate",
                "skipped",
                summary="Reused cached analysis artifacts",
            )
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s4_static",
                "skipped",
                summary="Reused cached static analysis",
            )
            return DiscoveryArtifacts(
                target=ctx.target,
                bundles=bundles,
                bundle_hashes=ctx.bundle_hashes,
                static_results=ctx.static_results,
                analysis_cache_hit=True,
            )

        bundles, cached_static = await self._check_bundle_cache(bundles)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s3_deobfuscate", "running")
        ctx.state.current_stage_index = 2
        self._store.save(ctx.state)
        deob_result = await execute_stage_with_metrics(
            ctx,
            deob_stage,
            ctx.state,
            ctx.mode,
            bundles=bundles,
        )
        if not deob_result.success:
            ctx.result.error = deob_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s3_deobfuscate",
                "failed",
                summary=ctx.result.error or "",
            )
            return None
        bundles = deob_result.next_input.get("bundles", bundles)
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s3_deobfuscate",
            "completed",
            summary=deob_result.summary,
            artifacts=artifact_map(deob_result.artifacts),
        )

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s4_static", "running")
        ctx.state.current_stage_index = 3
        self._store.save(ctx.state)
        static_result = await execute_stage_with_metrics(
            ctx,
            static_stage,
            ctx.state,
            ctx.mode,
            bundles=bundles,
        )
        if not static_result.success:
            ctx.result.error = static_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s4_static",
                "failed",
                summary=ctx.result.error or "",
            )
            return None
        ctx.static_results = {
            **cached_static,
            **static_result.next_input.get("static_results", {}),
        }

        if (
            not self._routing_service.has_static_candidates(ctx.static_results)
            and fetch_result.next_input.get("can_expand")
            and ctx.target.execution_plan
            and ctx.target.execution_plan.tier == ExecutionTier.BROWSER_FULL
        ):
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s2_fetch",
                "running",
                summary="Static analysis found no candidates; expanding JS fetch window",
            )
            expanded_fetch = await execute_stage_with_metrics(
                ctx,
                fetch_stage,
                ctx.state,
                ctx.mode,
                target=ctx.target,
                expand=True,
            )
            if expanded_fetch.success:
                bundles = expanded_fetch.next_input.get("bundles", [])
                ctx.bundle_hashes = bundle_hashes(bundles)
                for bundle in bundles:
                    ctx.cost.add_bundle_bytes(bundle.size_bytes, stage="s2_fetch")
                bundles, cached_static = await self._check_bundle_cache(bundles)
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s2_fetch",
                    "completed",
                    summary=expanded_fetch.summary,
                    artifacts=artifact_map(expanded_fetch.artifacts),
                )
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s3_deobfuscate",
                    "running",
                    summary="Expanded pass",
                )
                deob_result = await execute_stage_with_metrics(
                    ctx,
                    deob_stage,
                    ctx.state,
                    ctx.mode,
                    bundles=bundles,
                )
                if not deob_result.success:
                    ctx.result.error = deob_result.error
                    return None
                bundles = deob_result.next_input.get("bundles", bundles)
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s4_static",
                    "running",
                    summary="Expanded pass",
                )
                static_result = await execute_stage_with_metrics(
                    ctx,
                    static_stage,
                    ctx.state,
                    ctx.mode,
                    bundles=bundles,
                )
                if not static_result.success:
                    ctx.result.error = static_result.error
                    return None
                ctx.static_results = {
                    **cached_static,
                    **static_result.next_input.get("static_results", {}),
                }

        self._analysis_cache.save(
            ctx.target,
            bundle_hashes=ctx.bundle_hashes,
            static_results=ctx.static_results,
        )
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s4_static",
            "completed",
            summary=static_result.summary,
            artifacts=artifact_map(static_result.artifacts),
        )
        return DiscoveryArtifacts(
            target=ctx.target,
            bundles=bundles,
            bundle_hashes=ctx.bundle_hashes,
            static_results=ctx.static_results,
            analysis_cache_hit=ctx.analysis_cache_hit,
        )

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
