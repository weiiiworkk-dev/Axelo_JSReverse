from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Type, TypeVar

import httpx
import structlog
from pydantic import BaseModel

from axelo.config import settings

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

# DeepSeek API 最大重试次数和退避参数
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class AIResponse(Generic[T]):
    data: T
    model: str
    input_tokens: int
    output_tokens: int
    response_id: str = ""


class AIClient:
    """DeepSeek API wrapper returning typed outputs."""

    # Map human-friendly / legacy aliases → actual DeepSeek API model names
    _MODEL_ALIASES: dict[str, str] = {
        "deepseek-v3": "deepseek-chat",      # deepseek-v3 is served as deepseek-chat
        "deepseek-v2": "deepseek-chat",
        "deepseek-v2.5": "deepseek-chat",
    }

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self._api_key = (api_key or "").strip()
        raw_model = (model or "deepseek-chat").strip()
        # Resolve alias so that AXELO_MODEL=deepseek-v3 still works
        self._model = self._MODEL_ALIASES.get(raw_model, raw_model)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post_with_retry(
        self,
        payload: dict,
        timeout: float = 90.0,
    ) -> dict:
        """发送请求并在限流/服务错误时以指数退避重试。"""
        if not self._api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY — set AXELO_DEEPSEEK_API_KEY in .env")

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers=self._auth_headers(),
                        json=payload,
                    )

                if response.status_code in _RETRY_STATUSES:
                    wait = 2 ** attempt
                    log.warning(
                        "deepseek_rate_limit_or_server_error",
                        status=response.status_code,
                        attempt=attempt + 1,
                        retry_after=wait,
                    )
                    await asyncio.sleep(wait)
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    continue

                response.raise_for_status()
                return response.json()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning(
                    "deepseek_network_error",
                    error=type(exc).__name__,
                    attempt=attempt + 1,
                    retry_after=wait,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(wait)

            except httpx.HTTPStatusError as exc:
                # 非重试状态码（如 401, 403）直接抛出
                raise

        raise last_exc or RuntimeError("DeepSeek request failed after all retries")

    @staticmethod
    def _extract_content(data: dict) -> str:
        """从响应中安全提取文本内容。"""
        choices = data.get("choices")
        if not choices or not isinstance(choices, list):
            raise ValueError(f"DeepSeek response missing 'choices': {list(data.keys())}")
        message = choices[0].get("message") or {}
        content = message.get("content", "").strip()
        if not content:
            raise ValueError("DeepSeek response content is empty")
        return content

    async def complete(self, prompt: str, max_tokens: int = 8192, temperature: float = 0.2) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post_with_retry(payload)
        return self._extract_content(data)

    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        output_schema: Type[T],
        tool_name: str = "output",
        max_tokens: int = 8192,
        log_dir: Path | None = None,
        enable_cache: bool = True,
    ) -> AIResponse[T]:
        schema = output_schema.model_json_schema()
        schema.pop("title", None)
        format_hint = json.dumps(schema, ensure_ascii=False, indent=2)
        composed_prompt = (
            f"{system_prompt}\n\n"
            "Return ONLY valid JSON for this schema:\n"
            f"{format_hint}\n\n"
            f"Task:\n{user_message}"
        )
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": composed_prompt}],
            "temperature": 0.2 if enable_cache else 0.3,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = await self._post_with_retry(payload)
        content = self._extract_content(data)

        try:
            result = output_schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, Exception) as exc:
            raise ValueError(f"Failed to parse DeepSeek response as {output_schema.__name__}: {exc}") from exc

        usage = data.get("usage", {})
        ai_response = AIResponse(
            data=result,
            model=self._model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            response_id=str(data.get("id", "")),
        )

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            try:
                (log_dir / f"{tool_name}_{ts}.json").write_text(
                    json.dumps(
                        {
                            "system": system_prompt[:500],
                            "user": user_message[:500],
                            "result": result.model_dump(),
                            "usage": {
                                "input": ai_response.input_tokens,
                                "output": ai_response.output_tokens,
                                "response_id": ai_response.response_id,
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                log.warning("ai_log_write_failed", error=str(exc))

        return ai_response


def get_client() -> AIClient:
    return AIClient(api_key=settings.deepseek_api_key, model=settings.model)
