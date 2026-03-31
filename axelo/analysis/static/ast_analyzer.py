from __future__ import annotations
import hashlib
from pathlib import Path
from axelo.models.analysis import FunctionSignature, StaticAnalysis
from axelo.analysis.static.call_graph import CallGraph
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants
from axelo.js_tools.runner import NodeRunner
import structlog

log = structlog.get_logger()


class ASTAnalyzer:
    """
    驱动 NodeRunner 提取 AST 元数据，然后在 Python 侧做：
    - FunctionSignature 构建
    - CallGraph 构建
    - TokenCandidate 打分
    """

    def __init__(self, runner: NodeRunner) -> None:
        self._runner = runner

    async def analyze(self, bundle_id: str, source_path: Path) -> StaticAnalysis:
        source = source_path.read_text(encoding="utf-8", errors="replace")

        log.info("ast_analyze_start", bundle_id=bundle_id, size=len(source))
        raw = await self._runner.extract_ast(source)

        if not raw.get("success"):
            log.warning("ast_extract_failed", bundle_id=bundle_id, error=raw.get("error"))
            return StaticAnalysis(bundle_id=bundle_id)

        # 构建 FunctionSignature map
        func_map: dict[str, FunctionSignature] = {}
        for fn in raw.get("functions", []):
            name = fn.get("name")
            line = fn.get("line", 0)
            # func_id = bundle_id:name_or_line
            func_id = f"{bundle_id}:{name or line}"
            if func_id in func_map:
                func_id = f"{bundle_id}:{name or line}@{line}"

            # 提取源码片段（按行号从原文中切割）
            snippet = _extract_snippet(source, line, context_lines=15)

            sig = FunctionSignature(
                func_id=func_id,
                name=name,
                source_file=str(source_path),
                line=line,
                col=fn.get("col", 0),
                params=fn.get("params", []),
                is_async=fn.get("isAsync", False),
                raw_source=snippet,
            )
            func_map[func_id] = sig

        # 调用图（暂用 NodeRunner 返回数据；更精确的需要额外 traverse）
        call_graph = CallGraph(func_map)

        # 对每个函数打分
        ast_meta = {
            "cryptoUsages": raw.get("cryptoUsages", []),
            "envAccess": raw.get("envAccess", []),
        }
        all_candidates = []
        for func in func_map.values():
            candidates = score_function(func, ast_meta)
            all_candidates.extend(candidates)

        # 按置信度排序，去重（同 func_id 只保留最高分）
        seen: set[str] = set()
        deduped = []
        for c in sorted(all_candidates, key=lambda x: -x.confidence):
            if c.func_id not in seen:
                seen.add(c.func_id)
                deduped.append(c)

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
            token_candidates=deduped[:20],  # 最多返回20个候选
            crypto_imports=raw.get("cryptoUsages", []),
            env_access=raw.get("envAccess", []),
            string_constants=interesting_strings,
        )


def _extract_snippet(source: str, start_line: int, context_lines: int = 15) -> str:
    """从源码中按行号提取代码片段"""
    lines = source.splitlines()
    idx = max(0, start_line - 1)
    end = min(len(lines), idx + context_lines)
    return "\n".join(lines[idx:end])
