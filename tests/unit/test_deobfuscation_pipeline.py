from __future__ import annotations

from pathlib import Path

import pytest

from axelo.js_tools.deobfuscators import DeobfuscationPipeline


class _FakeRunner:
    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, float]] = []

    async def deobfuscate(self, source: str, tool: str, *, timeout_sec: float = 25.0) -> dict:
        self.calls.append((tool, timeout_sec))
        response = self._responses[tool]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_plain_bundle_skips_webcrack_and_uses_babel_first(tmp_path: Path):
    runner = _FakeRunner(
        {
            "babel-manual": {
                "success": True,
                "code": "const value = 1;",
                "originalScore": 0.2,
                "outputScore": 0.45,
            },
            "synchrony": {
                "success": True,
                "code": "const value = 2;",
                "originalScore": 0.2,
                "outputScore": 0.3,
            },
        }
    )
    pipeline = DeobfuscationPipeline(runner)  # type: ignore[arg-type]

    result = await pipeline.run(
        "bundle-a",
        "function a(){return 1}",
        tmp_path,
        bundle_type="plain",
        size_bytes=150_000,
    )

    assert result.success is True
    assert result.tool_used == "babel-manual"
    assert [tool for tool, _ in runner.calls] == ["babel-manual"]


@pytest.mark.asyncio
async def test_webpack_bundle_prefers_webcrack(tmp_path: Path):
    runner = _FakeRunner(
        {
            "webcrack": {
                "success": True,
                "code": "const modules = {};",
                "originalScore": 0.25,
                "outputScore": 0.5,
            },
            "babel-manual": {
                "success": True,
                "code": "const other = {};",
                "originalScore": 0.25,
                "outputScore": 0.35,
            },
        }
    )
    pipeline = DeobfuscationPipeline(runner)  # type: ignore[arg-type]

    result = await pipeline.run(
        "bundle-b",
        "self.webpackChunk=self.webpackChunk||[];",
        tmp_path,
        bundle_type="webpack",
        size_bytes=80_000,
    )

    assert result.success is True
    assert result.tool_used == "webcrack"
    assert [tool for tool, _ in runner.calls] == ["webcrack"]


@pytest.mark.asyncio
async def test_timeout_falls_back_to_next_tool(tmp_path: Path):
    runner = _FakeRunner(
        {
            "webcrack": RuntimeError("Node 调用超时: deobfuscate"),
            "babel-manual": {
                "success": True,
                "code": "const stable = true;",
                "originalScore": 0.2,
                "outputScore": 0.5,
            },
        }
    )
    pipeline = DeobfuscationPipeline(runner)  # type: ignore[arg-type]

    result = await pipeline.run(
        "bundle-c",
        "__webpack_require__(1)",
        tmp_path,
        bundle_type="webpack",
        size_bytes=60_000,
    )
    assert result.success is True
    assert result.tool_used == "babel-manual"
    assert [tool for tool, _ in runner.calls] == ["webcrack", "babel-manual"]
