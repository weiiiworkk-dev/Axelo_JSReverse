from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
import httpx
import structlog
from axelo.config import settings

log = structlog.get_logger()

_METRICS_FILE = Path("artifacts") / "metrics.jsonl"


class LLMClient:
    """单一 LLM 接口，DeepSeek provider"""

    BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-chat"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self._model = model or self.DEFAULT_MODEL
        self._api_key = api_key or settings.deepseek_api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=120,
        )

    async def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        return await self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)

    async def chat(self, messages: list[dict], *, max_tokens: int = 4096) -> str:
        t0 = time.monotonic()
        resp = await self._client.post("/chat/completions", json={
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        })
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        content = data["choices"][0]["message"]["content"]
        await self._write_metrics(usage, time.monotonic() - t0)
        return content

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with self._client.stream("POST", "/chat/completions", json={
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta

    # DeepSeek pricing (USD per 1M tokens, as of 2025)
    _PRICING = {
        "deepseek-chat":  {"in": 0.14, "out": 0.28},
        "deepseek-coder": {"in": 0.14, "out": 0.28},
    }

    def _calc_cost(self, tokens_in: int, tokens_out: int) -> float:
        price = self._PRICING.get(self._model, {"in": 0.14, "out": 0.28})
        return (tokens_in * price["in"] + tokens_out * price["out"]) / 1_000_000

    async def _write_metrics(self, usage: dict, duration_s: float) -> None:
        _METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": self._model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(self._calc_cost(tokens_in, tokens_out), 6),
            "duration_s": round(duration_s, 3),
        }
        with open(_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def aclose(self) -> None:
        await self._client.aclose()
