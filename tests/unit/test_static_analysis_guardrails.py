from __future__ import annotations

from pathlib import Path

import pytest

from axelo.analysis.static.ast_analyzer import ASTAnalyzer
from axelo.models.analysis import StaticAnalysis
from axelo.models.bundle import JSBundle
from axelo.pipeline.stages.s4_static import _should_skip_bundle


class _TimeoutRunner:
    async def extract_ast(self, source: str) -> dict:
        raise TimeoutError("simulated timeout")


@pytest.mark.asyncio
async def test_ast_analyzer_returns_empty_result_on_timeout(tmp_path: Path):
    source_path = tmp_path / "sample.js"
    source_path.write_text("function demo(){ return 1; }", encoding="utf-8")

    analyzer = ASTAnalyzer(_TimeoutRunner())  # type: ignore[arg-type]
    result = await analyzer.analyze("bundle-x", source_path)

    assert isinstance(result, StaticAnalysis)
    assert result.bundle_id == "bundle-x"
    assert result.token_candidates == []


def test_static_stage_skips_large_plain_bundle():
    bundle = JSBundle(
        bundle_id="plain-big",
        source_url="https://example.com/aplus/tracker.js",
        raw_path=Path("plain-big.js"),
        size_bytes=180 * 1024,
        bundle_type="plain",
    )

    assert _should_skip_bundle(bundle) is True


def test_static_stage_keeps_small_webpack_bundle():
    bundle = JSBundle(
        bundle_id="webpack-small",
        source_url="https://example.com/app.js",
        raw_path=Path("webpack-small.js"),
        size_bytes=80 * 1024,
        bundle_type="webpack",
    )

    assert _should_skip_bundle(bundle) is False
