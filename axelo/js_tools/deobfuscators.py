from __future__ import annotations
import asyncio
import time
from pathlib import Path
import structlog

from axelo.js_tools.runner import NodeRunner
from axelo.models.bundle import DeobfuscationResult, DeobfuscatorName

log = structlog.get_logger()

# 去混淆工具优先级列表（按尝试顺序）
TOOL_PRIORITY: list[DeobfuscatorName] = ["webcrack", "synchrony", "babel-manual"]

# 可读性提升阈值：低于此值则尝试下一个工具
MIN_SCORE_IMPROVEMENT = 0.1


class DeobfuscationPipeline:
    """
    按优先级尝试多个去混淆工具，选择质量最高的结果。
    """

    def __init__(self, runner: NodeRunner) -> None:
        self._runner = runner

    async def run(
        self,
        bundle_id: str,
        source: str,
        output_dir: Path,
        force_tool: DeobfuscatorName | None = None,
    ) -> DeobfuscationResult:
        tools = [force_tool] if force_tool else TOOL_PRIORITY
        best: DeobfuscationResult | None = None

        for tool in tools:
            t0 = time.monotonic()
            try:
                raw = await self._runner.deobfuscate(source, tool)
            except Exception as e:
                log.warning("deobfuscate_tool_error", tool=tool, error=str(e))
                continue

            duration = time.monotonic() - t0
            result = DeobfuscationResult(
                bundle_id=bundle_id,
                tool_used=tool,
                success=raw.get("success", False),
                readability_score=raw.get("outputScore", 0.0),
                original_score=raw.get("originalScore", 0.0),
                error=raw.get("error"),
                duration_seconds=duration,
            )

            if result.success:
                out_path = output_dir / f"{bundle_id}.{tool}.js"
                out_path.write_text(raw["code"], encoding="utf-8")
                result.output_path = out_path

                improvement = result.readability_score - result.original_score
                log.info(
                    "deobfuscate_result",
                    tool=tool, bundle_id=bundle_id,
                    score=f"{result.readability_score:.2f}",
                    improvement=f"{improvement:+.2f}",
                )

                if best is None or result.readability_score > best.readability_score:
                    best = result

                if improvement >= MIN_SCORE_IMPROVEMENT:
                    break  # 质量足够，不再尝试其他工具

        if best is None:
            best = DeobfuscationResult(
                bundle_id=bundle_id,
                tool_used="none",
                success=False,
                error="所有去混淆工具均失败",
            )

        return best
