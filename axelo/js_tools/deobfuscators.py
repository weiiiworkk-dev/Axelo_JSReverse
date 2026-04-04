from __future__ import annotations

import re
import time
from pathlib import Path

import structlog

from axelo.js_tools.runner import NodeRunner
from axelo.models.bundle import BundleType, DeobfuscationResult, DeobfuscatorName

log = structlog.get_logger()

TOOL_PRIORITY: list[DeobfuscatorName] = ["webcrack", "synchrony", "babel-manual"]
MIN_SCORE_IMPROVEMENT = 0.1
WEBPACK_HINT = re.compile(r"__webpack_require__|webpackChunk|webpack_modules", re.S)
OBFUSCATOR_HINT = re.compile(r"_0x[a-f0-9]{3,}|String\.fromCharCode|atob\(", re.I)


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
        *,
        bundle_type: BundleType = "unknown",
        size_bytes: int | None = None,
        force_tool: DeobfuscatorName | None = None,
    ) -> DeobfuscationResult:
        effective_size = size_bytes or len(source.encode("utf-8", errors="ignore"))
        tools = [force_tool] if force_tool else self._select_tools(
            source=source,
            bundle_type=bundle_type,
            size_bytes=effective_size,
        )
        best: DeobfuscationResult | None = None

        for tool in tools:
            timeout_sec = self._timeout_for(tool, bundle_type=bundle_type, size_bytes=effective_size)
            t0 = time.monotonic()
            try:
                log.info(
                    "deobfuscate_attempt",
                    bundle_id=bundle_id,
                    tool=tool,
                    bundle_type=bundle_type,
                    size_bytes=effective_size,
                    timeout_sec=timeout_sec,
                )
                raw = await self._runner.deobfuscate(source, tool, timeout_sec=timeout_sec)
            except Exception as exc:
                log.warning(
                    "deobfuscate_tool_error",
                    bundle_id=bundle_id,
                    tool=tool,
                    bundle_type=bundle_type,
                    size_bytes=effective_size,
                    error=str(exc),
                )
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
                    bundle_id=bundle_id,
                    tool=tool,
                    bundle_type=bundle_type,
                    size_bytes=effective_size,
                    score=f"{result.readability_score:.2f}",
                    improvement=f"{improvement:+.2f}",
                )

                if best is None or result.readability_score > best.readability_score:
                    best = result

                if improvement >= MIN_SCORE_IMPROVEMENT:
                    break

        if best is None:
            best = DeobfuscationResult(
                bundle_id=bundle_id,
                tool_used="none",
                success=False,
                error="所有去混淆工具均失败",
            )

        return best

    def _select_tools(
        self,
        *,
        source: str,
        bundle_type: BundleType,
        size_bytes: int,
    ) -> list[DeobfuscatorName]:
        if size_bytes > 800_000:
            return ["babel-manual"]

        if bundle_type == "webpack" or WEBPACK_HINT.search(source):
            if size_bytes > 250_000:
                return ["babel-manual"]
            return ["webcrack", "babel-manual"]

        if OBFUSCATOR_HINT.search(source):
            if size_bytes > 220_000:
                return ["babel-manual"]
            return ["synchrony", "babel-manual"]

        if bundle_type in {"plain", "rollup", "vite", "esbuild", "unknown"}:
            if size_bytes > 180_000:
                return ["babel-manual"]
            return ["babel-manual", "synchrony"]

        return TOOL_PRIORITY

    def _timeout_for(
        self,
        tool: DeobfuscatorName,
        *,
        bundle_type: BundleType,
        size_bytes: int,
    ) -> float:
        if tool == "webcrack":
            return 35.0 if bundle_type == "webpack" and size_bytes <= 250_000 else 20.0
        if tool == "synchrony":
            return 20.0 if size_bytes <= 160_000 else 12.0
        if tool == "babel-manual":
            return 25.0 if size_bytes <= 250_000 else 18.0
        return 20.0
