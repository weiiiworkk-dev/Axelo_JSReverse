from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Type, TypeVar

import anthropic
import anyio
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
    """
    Anthropic SDK wrapper that returns typed tool outputs and real usage metadata.
    """

    def __init__(self, api_key: str, model: str = "claude-opus-4-6") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

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
        tool_schema = _pydantic_to_tool_schema(output_schema, tool_name)

        # Cost-A: Anthropic prompt caching — mark static system prompt as ephemeral cache block.
        # Cache hits are billed at 0.1× input price, saving ~45–65% on repeated calls with the same system prompt.
        system_content: str | list = system_prompt
        if enable_cache and system_prompt:
            system_content = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        t0 = time.monotonic()
        response = await anyio.to_thread.run_sync(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_content,
                messages=[{"role": "user", "content": user_message}],
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": tool_name},
            )
        )
        duration = time.monotonic() - t0

        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_created = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        log.info(
            "ai_call_done",
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=cache_read,
            cache_created_tokens=cache_created,
            duration=f"{duration:.1f}s",
        )

        tool_block = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_block is None:
            raise ValueError("AI response did not contain a tool_use block")

        result = output_schema.model_validate(tool_block.input)
        payload = AIResponse(
            data=result,
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            response_id=getattr(response, "id", ""),
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


def _pydantic_to_tool_schema(model: Type[BaseModel], name: str) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)
    return {
        "name": name,
        "description": f"Structured {model.__name__} output",
        "input_schema": schema,
    }
