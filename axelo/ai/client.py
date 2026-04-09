from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Type, TypeVar

import httpx
import structlog
from pydantic import BaseModel

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AIResponse(Generic[T]):
    data: T
    model: str
    input_tokens: int
    output_tokens: int
    response_id: str = ""


class AIClient:
    """DeepSeek API wrapper returning typed outputs."""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self._api_key = (api_key or "").strip()
        self._model = model or "deepseek-chat"

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
        if not self._api_key:
            raise ValueError("Missing DEEPSEEK_API_KEY")

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
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"].get("content", "").strip()
        if not content:
            raise ValueError("DeepSeek response content is empty")
        result = output_schema.model_validate(json.loads(content))
        usage = data.get("usage", {})
        payload = AIResponse(
            data=result,
            model=self._model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            response_id=str(data.get("id", "")),
        )

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            (log_dir / f"{tool_name}_{ts}.json").write_text(
                json.dumps(
                    {
                        "system": system_prompt[:500],
                        "user": user_message[:500],
                        "result": result.model_dump(),
                        "usage": {
                            "input": payload.input_tokens,
                            "output": payload.output_tokens,
                            "response_id": payload.response_id,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        return payload
