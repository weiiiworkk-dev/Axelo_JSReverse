from __future__ import annotations

import re
import structlog
from pydantic import BaseModel, Field

from axelo.agents.base import BaseAgent
from axelo.models.analysis import StaticAnalysis
from axelo.models.target import TargetSite

log = structlog.get_logger()


# Cost-D: Static rule patterns — if these match, skip AI call entirely
_SIMPLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\bbtoa\b|\batob\b'), "base64"),
    (re.compile(r'\bmd5\b', re.IGNORECASE), "md5"),
    (re.compile(r'\bsha256\b|\bsha-256\b', re.IGNORECASE), "sha256"),
    (re.compile(r'\bHmac\b|\bhmac\b'), "hmac"),
    (re.compile(r'\bAES\b|\baes\b'), "aes"),
]
_COMPLEX_PATTERNS: list[re.Pattern] = [
    re.compile(r'_0x[0-9a-fA-F]{4}'),     # obfuscated hex identifiers
    re.compile(r'eval\s*\('),              # eval() usage
    re.compile(r'Function\s*\('),          # Function() constructor
]


def _static_rule_scan(static_results: dict[str, StaticAnalysis]) -> ScanReport | None:
    """Quick regex-based scan. Returns ScanReport if confident, else None (fall back to AI)."""
    all_imports: list[str] = []
    all_candidates = []
    for static in static_results.values():
        all_imports.extend(static.crypto_imports)
        all_candidates.extend(static.token_candidates)
        for const in static.string_constants[:20]:
            for pattern, algo in _SIMPLE_PATTERNS:
                if pattern.search(const):
                    all_imports.append(algo)

    # Obfuscation check — if strongly obfuscated, return early with complex verdict
    joined = " ".join(all_imports + [c.func_id for c in all_candidates])
    is_obfuscated = any(pat.search(joined) for pat in _COMPLEX_PATTERNS)
    if is_obfuscated:
        return None  # Defer to AI

    # Simple algorithm detection
    detected: list[str] = []
    for _, algo in _SIMPLE_PATTERNS:
        if any(algo.lower() in imp.lower() for imp in all_imports):
            detected.append(algo)

    if not detected and not all_candidates:
        return None  # Not enough signal

    complexity = "simple" if len(all_candidates) <= 2 else "moderate"
    difficulty = "easy" if detected else "medium"
    return ScanReport(
        bundle_complexity=complexity,
        detected_frameworks=[],
        crypto_libs=detected,
        interesting_functions=[c.func_id for c in all_candidates[:5]],
        token_field_hints=[c.request_field for c in all_candidates if c.request_field][:5],
        priority_bundles=list(static_results.keys())[:3],
        quick_verdict=f"Static rules detected: {', '.join(detected) or 'standard patterns'}",
        estimated_difficulty=difficulty,
    )


class ScanReport(BaseModel):
    bundle_complexity: str = Field(description="bundle complexity: simple/moderate/complex/obfuscated")
    detected_frameworks: list[str] = Field(default_factory=list, description="Detected JS frameworks/libraries")
    crypto_libs: list[str] = Field(default_factory=list, description="Detected crypto libraries")
    interesting_functions: list[str] = Field(default_factory=list, description="Function IDs worth deeper analysis")
    token_field_hints: list[str] = Field(default_factory=list, description="Likely token header/param fields")
    priority_bundles: list[str] = Field(default_factory=list, description="Bundle IDs to prioritize")
    quick_verdict: str = Field(description="Short verdict about whether deeper analysis is worthwhile")
    estimated_difficulty: str = Field(description="Estimated difficulty: easy/medium/hard/extreme")


SCANNER_SYSTEM = """你是一位 JS 逆向扫描器（Scanner）。
你的工作是快速扫描 JS bundle 特征，给出第一印象评估。

## BM25 关键词检索命中的相似模板（供参考）
{bm25_context}
"""


class ScannerAgent(BaseAgent):
    role = "scanner"
    default_model = "claude-haiku-4-5"

    def __init__(self, *args, retriever=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever

    async def scan(
        self,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
    ) -> ScanReport:
        # Cost-D: try static rules first — skip AI for ~50% of simple bundles
        rule_result = _static_rule_scan(static_results)
        if rule_result is not None:
            log.info("scanner_rules_matched", complexity=rule_result.bundle_complexity, algos=rule_result.crypto_libs)
            return rule_result

        bm25_context = self._bm25_lookup(static_results)

        parts = [f"URL: {target.url}", f"目标: {target.interaction_goal}", ""]
        for bundle_id, static in static_results.items():
            parts.append(f"Bundle {bundle_id}:")
            parts.append(f"  Crypto: {static.crypto_imports[:5]}")
            parts.append(f"  Env: {static.env_access[:5]}")
            parts.append(f"  Candidates: {len(static.token_candidates)}")
            if static.token_candidates:
                top = static.token_candidates[0]
                parts.append(f"  Top candidate: {top.func_id} ({top.token_type}, {top.confidence:.0%})")
            if static.string_constants:
                parts.append(f"  Strings: {static.string_constants[:3]}")

        context = "\n".join(parts)
        client = self._build_client()
        response = await client.analyze(
            system_prompt=SCANNER_SYSTEM.format(bm25_context=bm25_context),
            user_message=f"请扫描以下 JS bundle 特征：\n\n{context}",
            output_schema=ScanReport,
            tool_name="scan_report",
            max_tokens=512,   # Cost-E: ScanReport is structured + small, 400 tokens max
        )
        result = response.data

        self._cost.add_ai_call(
            model=response.model,
            input_tok=response.input_tokens,
            output_tok=response.output_tokens,
            stage="scanner",
        )

        log.info(
            "scanner_done",
            difficulty=result.estimated_difficulty,
            interesting=len(result.interesting_functions),
            bm25_used=bool(bm25_context.strip()),
        )
        return result

    def _bm25_lookup(self, static_results: dict[str, StaticAnalysis]) -> str:
        if self._retriever is None:
            return "(no historical templates)"

        keywords: list[str] = []
        for static in static_results.values():
            keywords.extend(static.crypto_imports[:5])
            keywords.extend(static.env_access[:3])
            for candidate in static.token_candidates[:3]:
                keywords.append(candidate.token_type)
                if candidate.request_field:
                    keywords.append(candidate.request_field)

        if not keywords:
            return "(no keywords)"

        query = " ".join(dict.fromkeys(keywords))
        templates = self._retriever.bm25_search_templates(query)
        if not templates:
            return "(no matched templates)"

        lines = [f"BM25 hit {len(templates)} similar templates:"]
        for template in templates:
            lines.append(f"  - {template.name}: {template.description} (algo: {template.algorithm_type})")
            if template.input_fields:
                lines.append(f"    inputs: {template.input_fields}")
        return "\n".join(lines)
