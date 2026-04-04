from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from axelo.analysis.static.call_graph import CallGraph
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants
from axelo.config import settings
from axelo.js_tools.runner import NodeRunner
from axelo.models.analysis import FunctionSignature, StaticAnalysis

log = structlog.get_logger()


class ASTAnalyzer:
    """
    驱动 NodeRunner 提取 AST 元数据，再由 Python 侧构建候选函数与静态特征。
    """

    def __init__(self, runner: NodeRunner) -> None:
        self._runner = runner

    async def analyze(self, bundle_id: str, source_path: Path) -> StaticAnalysis:
        source = source_path.read_text(encoding="utf-8", errors="replace")
        source = _prepare_source_sample(source)

        log.info("ast_analyze_start", bundle_id=bundle_id, size=len(source))
        try:
            raw = await asyncio.wait_for(
                self._runner.extract_ast(source),
                timeout=settings.ast_extract_timeout_sec,
            )
        except Exception as exc:
            log.warning("ast_extract_error", bundle_id=bundle_id, error=str(exc))
            return StaticAnalysis(bundle_id=bundle_id)

        if not raw.get("success"):
            log.warning("ast_extract_failed", bundle_id=bundle_id, error=raw.get("error"))
            return StaticAnalysis(bundle_id=bundle_id)

        func_map: dict[str, FunctionSignature] = {}
        for fn in raw.get("functions", []):
            name = fn.get("name")
            line = fn.get("line", 0)
            func_id = f"{bundle_id}:{name or line}"
            if func_id in func_map:
                func_id = f"{bundle_id}:{name or line}@{line}"

            snippet = _extract_snippet(source, line, context_lines=15)
            func_map[func_id] = FunctionSignature(
                func_id=func_id,
                name=name,
                source_file=str(source_path),
                line=line,
                col=fn.get("col", 0),
                params=fn.get("params", []),
                is_async=fn.get("isAsync", False),
                raw_source=snippet,
            )

        CallGraph(func_map)

        ast_meta = {
            "cryptoUsages": raw.get("cryptoUsages", []),
            "envAccess": raw.get("envAccess", []),
        }
        all_candidates = []
        for func in func_map.values():
            all_candidates.extend(score_function(func, ast_meta))

        seen: set[str] = set()
        deduped = []
        for candidate in sorted(all_candidates, key=lambda item: -item.confidence):
            if candidate.func_id in seen:
                continue
            seen.add(candidate.func_id)
            deduped.append(candidate)

        interesting_strings = scan_string_constants(raw.get("stringLiterals", []))

        log.info(
            "ast_analyze_done",
            bundle_id=bundle_id,
            funcs=len(func_map),
            candidates=len(deduped),
        )

        return StaticAnalysis(
            bundle_id=bundle_id,
            function_map=func_map,
            token_candidates=deduped[:20],
            crypto_imports=raw.get("cryptoUsages", []),
            env_access=raw.get("envAccess", []),
            string_constants=interesting_strings,
        )


def _extract_snippet(source: str, start_line: int, context_lines: int = 15) -> str:
    lines = source.splitlines()
    index = max(0, start_line - 1)
    end = min(len(lines), index + context_lines)
    return "\n".join(lines[index:end])


def _prepare_source_sample(source: str, max_chars: int = 120_000) -> str:
    if len(source) <= max_chars:
        return source
    head = source[:80_000]
    tail = source[-40_000:]
    return head + "\n/* ... axelo truncated oversized bundle for AST analysis ... */\n" + tail
