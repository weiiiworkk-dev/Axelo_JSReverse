from __future__ import annotations
import json
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.bundle import JSBundle
from axelo.models.analysis import StaticAnalysis
from axelo.modes.base import ModeController
from axelo.analysis.static.ast_analyzer import ASTAnalyzer
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()


class StaticAnalysisStage(PipelineStage):
    name = "s4_static"
    description = "静态AST分析：提取函数调用图，识别Token候选函数"

    def __init__(self, analyzer: ASTAnalyzer) -> None:
        self._analyzer = analyzer

    async def run(
        self, state: PipelineState, mode: ModeController,
        bundles: list[JSBundle], **_
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        ast_dir = session_dir / "ast"
        ast_dir.mkdir(parents=True, exist_ok=True)

        static_results: dict[str, StaticAnalysis] = {}

        for bundle in bundles:
            source_path = bundle.deobfuscated_path or bundle.raw_path
            if not source_path or not source_path.exists():
                log.warning("no_source_for_bundle", bundle_id=bundle.bundle_id)
                continue

            sa = await self._analyzer.analyze(bundle.bundle_id, source_path)
            static_results[bundle.bundle_id] = sa

            # 保存分析结果
            result_path = ast_dir / f"{bundle.bundle_id}_static.json"
            result_path.write_text(sa.model_dump_json(indent=2), encoding="utf-8")

        # 汇总所有候选函数展示给用户
        all_candidates = []
        for sa in static_results.values():
            all_candidates.extend(sa.token_candidates)
        all_candidates.sort(key=lambda c: -c.confidence)

        if not all_candidates:
            return StageResult(
                stage_name=self.name,
                success=True,
                summary="静态分析完成，未发现明显候选函数（可能需要动态分析）",
                next_input={"static_results": static_results},
            )

        options = [
            f"[{i+1}] {c.func_id} | {c.token_type} | {c.confidence:.0%} | {c.request_field or '未知字段'}"
            for i, c in enumerate(all_candidates[:12])
        ]
        options.append("接受所有候选")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.OVERRIDE_HYPOTHESIS,
            prompt=f"静态分析发现 {len(all_candidates)} 个候选函数，请确认或调整：",
            options=options,
            context_summary="\n".join(
                f"  • {c.func_id}: {'; '.join(c.evidence[:2])}"
                for c in all_candidates[:5]
            ),
            default="接受所有候选",
        )

        outcome = await mode.gate(decision, state)

        # 根据选择过滤候选（仅在单选时过滤，多选暂不支持，保留全部）
        # 后续 AI 分析阶段会进一步筛选

        static_path = ast_dir / "static_summary.json"
        static_path.write_text(
            json.dumps(
                {bid: sa.model_dump(mode="json") for bid, sa in static_results.items()},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"static_results": static_path},
            decisions=[decision],
            summary=f"分析 {len(bundles)} 个bundle，发现 {len(all_candidates)} 个候选函数",
            next_input={"static_results": static_results},
        )
