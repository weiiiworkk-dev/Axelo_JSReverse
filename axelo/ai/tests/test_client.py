"""Unit tests for axelo.ai.client.LLMClient"""
from __future__ import annotations

import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

from axelo.ai.client import LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chat_response(content: str = "hello", tokens_in: int = 10, tokens_out: int = 5) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComplete:
    """complete() should delegate to chat() with correct message shape."""

    @pytest.mark.asyncio
    async def test_complete_calls_chat_with_user_message(self):
        client = LLMClient(model="deepseek-chat", api_key="test-key")

        # Patch chat() to capture arguments
        client.chat = AsyncMock(return_value="response text")

        result = await client.complete("hello world", max_tokens=1024)

        client.chat.assert_called_once_with(
            [{"role": "user", "content": "hello world"}],
            max_tokens=1024,
        )
        assert result == "response text"

    @pytest.mark.asyncio
    async def test_complete_default_max_tokens(self):
        client = LLMClient(model="deepseek-chat", api_key="test-key")
        client.chat = AsyncMock(return_value="ok")

        await client.complete("test")

        _, kwargs = client.chat.call_args
        assert kwargs["max_tokens"] == 4096


class TestWriteMetrics:
    """_write_metrics() should write a JSONL entry with cost_usd field."""

    @pytest.mark.asyncio
    async def test_write_metrics_contains_cost_usd(self, tmp_path):
        client = LLMClient(model="deepseek-chat", api_key="test-key")

        # Override the metrics file path to use tmp_path
        metrics_file = tmp_path / "metrics.jsonl"

        import axelo.ai.client as client_module
        original = client_module._METRICS_FILE
        client_module._METRICS_FILE = metrics_file

        try:
            await client._write_metrics(
                {"prompt_tokens": 100, "completion_tokens": 50},
                duration_s=1.23,
            )
        finally:
            client_module._METRICS_FILE = original

        assert metrics_file.exists()
        line = metrics_file.read_text(encoding="utf-8").strip()
        entry = json.loads(line)

        assert "cost_usd" in entry
        assert entry["tokens_in"] == 100
        assert entry["tokens_out"] == 50
        assert entry["model"] == "deepseek-chat"
        assert entry["duration_s"] == pytest.approx(1.23, abs=0.001)
        # cost = (100 * 0.14 + 50 * 0.28) / 1_000_000
        expected_cost = round((100 * 0.14 + 50 * 0.28) / 1_000_000, 6)
        assert entry["cost_usd"] == expected_cost

    @pytest.mark.asyncio
    async def test_write_metrics_creates_parent_dir(self, tmp_path):
        client = LLMClient(model="deepseek-chat", api_key="test-key")

        nested = tmp_path / "nested" / "dir" / "metrics.jsonl"

        import axelo.ai.client as client_module
        original = client_module._METRICS_FILE
        client_module._METRICS_FILE = nested

        try:
            await client._write_metrics({}, duration_s=0.5)
        finally:
            client_module._METRICS_FILE = original

        assert nested.exists()


class TestStream:
    """stream() should yield delta chunks from SSE lines."""

    @pytest.mark.asyncio
    async def test_stream_yields_deltas(self):
        client = LLMClient(model="deepseek-chat", api_key="test-key")

        # Build fake SSE lines
        sse_lines = [
            'data: ' + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}),
            'data: ' + json.dumps({"choices": [{"delta": {"content": " world"}}]}),
            'data: ' + json.dumps({"choices": [{"delta": {}}]}),  # empty delta — should be skipped
            'data: [DONE]',
        ]

        # Mock the streaming context manager
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = fake_aiter_lines

        class FakeStreamCtx:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        client._client.stream = MagicMock(return_value=FakeStreamCtx())

        chunks = []
        async for chunk in client.stream("say hello"):
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_skips_non_data_lines(self):
        client = LLMClient(model="deepseek-chat", api_key="test-key")

        sse_lines = [
            ': keep-alive',
            '',
            'data: ' + json.dumps({"choices": [{"delta": {"content": "chunk"}}]}),
            'data: [DONE]',
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = fake_aiter_lines

        class FakeStreamCtx:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        client._client.stream = MagicMock(return_value=FakeStreamCtx())

        chunks = []
        async for chunk in client.stream("test"):
            chunks.append(chunk)

        assert chunks == ["chunk"]
