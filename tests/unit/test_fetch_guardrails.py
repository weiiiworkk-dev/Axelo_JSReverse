from __future__ import annotations

import pytest

from axelo.models.bundle import JSBundle
from axelo.models.execution import ExecutionPlan
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s2_fetch import _apply_bundle_caps, _download_bundle_bytes


def test_bundle_guardrails_skip_oversized_entries(tmp_path):
    bundles = [
        JSBundle(bundle_id="a", source_url="https://a.js", raw_path=tmp_path / "a.js", size_bytes=120 * 1024, bundle_type="webpack"),
        JSBundle(bundle_id="b", source_url="https://b.js", raw_path=tmp_path / "b.js", size_bytes=700 * 1024, bundle_type="rollup"),
        JSBundle(bundle_id="c", source_url="https://c.js", raw_path=tmp_path / "c.js", size_bytes=140 * 1024, bundle_type="plain"),
        JSBundle(bundle_id="d", source_url="https://d.js", raw_path=tmp_path / "d.js", size_bytes=160 * 1024, bundle_type="plain"),
    ]
    target = TargetSite(url="https://example.com", session_id="s01", interaction_goal="demo")
    target.execution_plan = ExecutionPlan(max_bundles=2, max_bundle_size_kb=256, max_total_bundle_kb=320)

    selected, note = _apply_bundle_caps(bundles, target)
    assert [bundle.bundle_id for bundle in selected] == ["a", "c"]
    assert "skipped" in note


class _FakeStreamResponse:
    def __init__(self, status_code: int, headers: dict[str, str], chunks: list[bytes]) -> None:
        self.status_code = status_code
        self.headers = headers
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    def stream(self, method: str, url: str, headers: dict[str, str]):
        return self._response


@pytest.mark.asyncio
async def test_download_bundle_skips_large_content_length():
    response = _FakeStreamResponse(
        status_code=200,
        headers={"Content-Length": "4096"},
        chunks=[b"console.log('ignored');"],
    )

    result = await _download_bundle_bytes(
        _FakeClient(response),  # type: ignore[arg-type]
        "https://example.com/app.js",
        referer="https://example.com",
        byte_limit=1024,
    )

    assert result is None


@pytest.mark.asyncio
async def test_download_bundle_skips_stream_that_exceeds_limit():
    response = _FakeStreamResponse(
        status_code=200,
        headers={},
        chunks=[b"a" * 600, b"b" * 600],
    )

    result = await _download_bundle_bytes(
        _FakeClient(response),  # type: ignore[arg-type]
        "https://example.com/app.js",
        referer="https://example.com",
        byte_limit=1024,
    )

    assert result is None


@pytest.mark.asyncio
async def test_download_bundle_returns_bytes_when_within_limit():
    response = _FakeStreamResponse(
        status_code=200,
        headers={"Content-Length": "12"},
        chunks=[b"hello ", b"world!"],
    )

    result = await _download_bundle_bytes(
        _FakeClient(response),  # type: ignore[arg-type]
        "https://example.com/app.js",
        referer="https://example.com",
        byte_limit=1024,
    )

    assert result == b"hello world!"
