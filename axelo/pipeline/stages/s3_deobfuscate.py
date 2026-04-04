from __future__ import annotations

from pathlib import Path

import structlog

from axelo.config import settings
from axelo.js_tools.deobfuscators import DeobfuscationPipeline
from axelo.js_tools.runner import NodeRunner
from axelo.models.bundle import DeobfuscationResult, JSBundle
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()


class DeobfuscateStage(PipelineStage):
    name = "s3_deobfuscate"
    description = "对 JS Bundle 进行去混淆（按类型智能选择工具）"

    def __init__(self, runner: NodeRunner) -> None:
        self._runner = runner
        self._pipeline = DeobfuscationPipeline(runner)

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        bundles: list[JSBundle],
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        deob_dir = session_dir / "bundles" / "deobfuscated"
        deob_dir.mkdir(parents=True, exist_ok=True)

        results: list[DeobfuscationResult] = []
        updated_bundles: list[JSBundle] = []

        for bundle in bundles:
            source = bundle.raw_path.read_text(encoding="utf-8", errors="replace")
            result = await self._pipeline.run(
                bundle.bundle_id,
                source,
                deob_dir,
                bundle_type=bundle.bundle_type,
                size_bytes=bundle.size_bytes,
            )
            results.append(result)

            if result.success and result.output_path:
                bundle.deobfuscated_path = result.output_path
            else:
                bundle.deobfuscated_path = bundle.raw_path
            updated_bundles.append(bundle)

        success_count = sum(1 for result in results if result.success)
        summary_lines = [
            (
                f"{result.bundle_id}: {result.tool_used} | "
                f"可读性 {result.original_score:.2f}->{result.readability_score:.2f}"
                + (f" ✓" if result.success else f" ✗ {result.error}")
            )
            for result in results
        ]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.APPROVE_STAGE,
            prompt="去混淆完成，请确认结果质量：",
            options=["接受结果，继续分析", "重试（换工具）", "跳过去混淆，使用原始代码"],
            context_summary="\n".join(summary_lines),
            default="接受结果，继续分析",
        )

        outcome = await mode.gate(decision, state)

        if outcome == "重试（换工具）":
            log.info("deobfuscate_retry")
            for bundle in updated_bundles:
                if not bundle.raw_path.exists():
                    continue
                source = bundle.raw_path.read_text(encoding="utf-8", errors="replace")
                retry = await self._pipeline.run(
                    bundle.bundle_id,
                    source,
                    deob_dir,
                    bundle_type=bundle.bundle_type,
                    size_bytes=bundle.size_bytes,
                    force_tool="babel-manual",
                )
                if retry.success and retry.output_path:
                    bundle.deobfuscated_path = retry.output_path
                else:
                    bundle.deobfuscated_path = bundle.raw_path

        elif outcome == "跳过去混淆，使用原始代码":
            for bundle in updated_bundles:
                bundle.deobfuscated_path = bundle.raw_path

        return StageResult(
            stage_name=self.name,
            success=True,
            decisions=[decision],
            summary=f"去混淆完成 {success_count}/{len(bundles)} 个 bundle",
            next_input={"bundles": updated_bundles},
        )
