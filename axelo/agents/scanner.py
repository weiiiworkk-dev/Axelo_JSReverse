from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from axelo.agents.base import BaseAgent
from axelo.models.analysis import StaticAnalysis
from axelo.models.target import TargetSite

log = structlog.get_logger()


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
            max_tokens=2048,
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
