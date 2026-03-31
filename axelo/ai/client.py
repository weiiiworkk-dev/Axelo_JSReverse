from __future__ import annotations
import json
import time
from pathlib import Path
from typing import TypeVar, Type
import anthropic
from pydantic import BaseModel
import structlog

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class AIClient:
    """
    Anthropic SDK 封装。
    使用 tool_use（函数调用）获取结构化输出，避免 JSON 解析脆弱性。
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
    ) -> T:
        """
        发送分析请求，通过 tool_use 获取类型安全的结构化输出。
        """
        tool_schema = _pydantic_to_tool_schema(output_schema, tool_name)

        t0 = time.monotonic()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
        )
        duration = time.monotonic() - t0

        log.info(
            "ai_call_done",
            model=self._model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            duration=f"{duration:.1f}s",
        )

        # 提取 tool_use 块
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise ValueError("AI 响应中未找到 tool_use 块")

        result = output_schema.model_validate(tool_block.input)

        # 可选：记录原始请求/响应到文件
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            (log_dir / f"{tool_name}_{ts}.json").write_text(
                json.dumps({
                    "system": system_prompt[:500],
                    "user": user_message[:500],
                    "result": result.model_dump(),
                    "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return result


def _pydantic_to_tool_schema(model: Type[BaseModel], name: str) -> dict:
    """将 Pydantic 模型转换为 Anthropic tool 定义"""
    schema = model.model_json_schema()
    # 移除 Anthropic 不需要的字段
    schema.pop("title", None)
    return {
        "name": name,
        "description": f"输出 {model.__name__} 结构",
        "input_schema": schema,
    }
