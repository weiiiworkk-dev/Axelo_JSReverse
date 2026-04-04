from __future__ import annotations

import json

import structlog

from axelo.analysis.static.ast_analyzer import ASTAnalyzer
from axelo.config import settings
from axelo.models.analysis import StaticAnalysis
from axelo.models.bundle import JSBundle
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()

_ANALYTICS_HINTS = ("aplus", "goldlog", "itrace", "tracker", "analytics", "monitor", "report")


class StaticAnalysisStage(PipelineStage):
    name = "s4_static"
    description = "静态 AST 分析：提取函数候选并识别潜在签名逻辑"

    def __init__(self, analyzer: ASTAnalyzer) -> None:
        self._analyzer = analyzer

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        bundles: list[JSBundle],
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        ast_dir = session_dir / "ast"
        ast_dir.mkdir(parents=True, exist_ok=True)

        static_results: dict[str, StaticAnalysis] = {}
        skipped_bundles: list[str] = []

        for bundle in _prioritize_for_static(bundles):
            source_path = bundle.deobfuscated_path or bundle.raw_path
            if not source_path or not source_path.exists():
                log.warning("no_source_for_bundle", bundle_id=bundle.bundle_id)
                continue

            if _should_skip_bundle(bundle):
                log.info(
                    "static_bundle_skipped",
                    bundle_id=bundle.bundle_id,
                    bundle_type=bundle.bundle_type,
                    size_bytes=bundle.size_bytes,
                    source_url=bundle.source_url,
                )
                static_results[bundle.bundle_id] = StaticAnalysis(bundle_id=bundle.bundle_id)
                skipped_bundles.append(bundle.bundle_id)
                continue

            static_analysis = await self._analyzer.analyze(bundle.bundle_id, source_path)
            static_results[bundle.bundle_id] = static_analysis

            result_path = ast_dir / f"{bundle.bundle_id}_static.json"
            result_path.write_text(static_analysis.model_dump_json(indent=2), encoding="utf-8")

        all_candidates = []
        for static_analysis in static_results.values():
            all_candidates.extend(static_analysis.token_candidates)
        all_candidates.sort(key=lambda candidate: -candidate.confidence)

        static_path = ast_dir / "static_summary.json"
        static_path.write_text(
            json.dumps(
                {bundle_id: analysis.model_dump(mode="json") for bundle_id, analysis in static_results.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if not all_candidates:
            skipped_note = f"，跳过 {len(skipped_bundles)} 个低价值 bundle" if skipped_bundles else ""
            return StageResult(
                stage_name=self.name,
                success=True,
                artifacts={"static_results": static_path},
                summary=f"静态分析完成，未发现明显候选函数{skipped_note}",
                next_input={"static_results": static_results},
            )

        options = [
            f"[{index + 1}] {candidate.func_id} | {candidate.token_type} | "
            f"{candidate.confidence:.0%} | {candidate.request_field or '未知字段'}"
            for index, candidate in enumerate(all_candidates[:12])
        ]
        options.append("接受所有候选")

        summary_bits = [
            *(f"- {candidate.func_id}: {'; '.join(candidate.evidence[:2])}" for candidate in all_candidates[:5]),
        ]
        if skipped_bundles:
            summary_bits.append(f"- 已跳过 {len(skipped_bundles)} 个低价值 bundle")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.OVERRIDE_HYPOTHESIS,
            prompt=f"静态分析发现 {len(all_candidates)} 个候选函数，请确认或调整：",
            options=options,
            context_summary="\n".join(summary_bits),
            default="接受所有候选",
        )

        await mode.gate(decision, state)

        skipped_note = f"，跳过 {len(skipped_bundles)} 个低价值 bundle" if skipped_bundles else ""
        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"static_results": static_path},
            decisions=[decision],
            summary=f"分析 {len(static_results)} 个 bundle，发现 {len(all_candidates)} 个候选函数{skipped_note}",
            next_input={"static_results": static_results},
        )


def _prioritize_for_static(bundles: list[JSBundle]) -> list[JSBundle]:
    type_rank = {"webpack": 0, "rollup": 1, "vite": 2, "esbuild": 3, "plain": 4, "unknown": 5}
    return sorted(
        bundles,
        key=lambda bundle: (
            type_rank.get(bundle.bundle_type, 6),
            abs(bundle.size_bytes - 90_000),
        ),
    )


def _should_skip_bundle(bundle: JSBundle) -> bool:
    url = bundle.source_url.lower()
    if bundle.bundle_type == "plain" and bundle.size_bytes >= 140_000:
        return True
    if bundle.bundle_type == "plain" and any(keyword in url for keyword in _ANALYTICS_HINTS):
        return True
    return False
