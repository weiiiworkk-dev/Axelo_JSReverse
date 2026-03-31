from __future__ import annotations
from pathlib import Path
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.bundle import JSBundle, DeobfuscationResult
from axelo.modes.base import ModeController
from axelo.js_tools.runner import NodeRunner
from axelo.js_tools.deobfuscators import DeobfuscationPipeline
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()


class DeobfuscateStage(PipelineStage):
    name = "s3_deobfuscate"
    description = "对JS Bundle进行去混淆（webcrack→synchrony→babel-manual）"

    def __init__(self, runner: NodeRunner) -> None:
        self._runner = runner
        self._pipeline = DeobfuscationPipeline(runner)

    async def run(
        self, state: PipelineState, mode: ModeController,
        bundles: list[JSBundle], **_
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        deob_dir = session_dir / "bundles" / "deobfuscated"
        deob_dir.mkdir(parents=True, exist_ok=True)

        results: list[DeobfuscationResult] = []
        updated_bundles: list[JSBundle] = []

        for bundle in bundles:
            source = bundle.raw_path.read_text(encoding="utf-8", errors="replace")
            result = await self._pipeline.run(bundle.bundle_id, source, deob_dir)
            results.append(result)

            if result.success and result.output_path:
                bundle.deobfuscated_path = result.output_path
            updated_bundles.append(bundle)

        # 汇总结果
        success_count = sum(1 for r in results if r.success)
        summary_lines = [
            f"{r.bundle_id}: {r.tool_used} | 可读性 {r.original_score:.2f}→{r.readability_score:.2f}"
            + (f" ✓" if r.success else f" ✗ {r.error}")
            for r in results
        ]

        context = "\n".join(summary_lines)
        options = ["接受结果，继续分析", "重试（换工具）", "跳过去混淆，使用原始代码"]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.APPROVE_STAGE,
            prompt="去混淆完成，请确认结果质量：",
            options=options,
            context_summary=context,
            default="接受结果，继续分析",
        )

        outcome = await mode.gate(decision, state)

        if outcome == options[1]:
            # 重试：强制使用 babel-manual
            log.info("deobfuscate_retry")
            for bundle in updated_bundles:
                if bundle.raw_path.exists():
                    source = bundle.raw_path.read_text(encoding="utf-8", errors="replace")
                    retry = await self._pipeline.run(bundle.bundle_id, source, deob_dir, force_tool="babel-manual")
                    if retry.success and retry.output_path:
                        bundle.deobfuscated_path = retry.output_path

        elif outcome == options[2]:
            # 跳过去混淆：使用原始文件
            for bundle in updated_bundles:
                bundle.deobfuscated_path = bundle.raw_path

        return StageResult(
            stage_name=self.name,
            success=True,
            decisions=[decision],
            summary=f"去混淆完成 {success_count}/{len(bundles)} 个bundle",
            next_input={"bundles": updated_bundles},
        )
