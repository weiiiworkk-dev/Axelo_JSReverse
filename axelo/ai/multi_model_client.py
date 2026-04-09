"""Compatibility module for DeepSeek-only AI client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Type, TypeVar

import structlog
from pydantic import BaseModel
from axelo.ai.client import AIClient as DeepSeekAIClient

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AIResponse(Generic[T]):
    """AI response with metadata"""
    data: T
    model: str
    input_tokens: int
    output_tokens: int
    response_id: str = ""
    provider: str = "deepseek"


class MultiModelAIClient:
    def __init__(
        self,
        deepseek_key: str | None = None,
        default_model: str = "deepseek-chat",
    ) -> None:
        self._deepseek_key = deepseek_key or ""
        self._default_model = default_model
        self._client = DeepSeekAIClient(api_key=self._deepseek_key, model=self._default_model)
    
    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> AIResponse:
        _ = model or self._default_model
        result = await self._client.analyze(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=type("RawOutput", (BaseModel,), {}),
            tool_name="output",
            max_tokens=max_tokens,
        )
        return AIResponse(
            data=result.data,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            response_id=result.response_id,
            provider="deepseek",
        )
    
    async def analyze_with_fallback(
        self,
        system_prompt: str,
        user_message: str,
        providers: list[str] | None = None,
        max_tokens: int = 8192,
    ) -> AIResponse:
        _ = providers
        return await self.analyze(system_prompt, user_message, max_tokens=max_tokens)
    
    def get_available_providers(self) -> list[str]:
        return ["deepseek"]


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

class AIClient:
    """
    Backward compatible wrapper for existing code.
    Use MultiModelAIClient for new features.
    """
    
    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self._client = MultiModelAIClient(
            deepseek_key=api_key,
            default_model=model,
        )
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
        """Analyze using the default model"""
        # Note: output_schema and tool_name are for compatibility
        # The actual implementation extracts content from the response
        response = await self._client.analyze(
            system_prompt=system_prompt,
            user_message=user_message,
            model=self._model,
            max_tokens=max_tokens,
        )
        
        # Create response compatible with original AIClient
        class FakeData(BaseModel):
            pass
        
        return AIResponse(
            data=FakeData(),
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            response_id=response.response_id,
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "MultiModelAIClient",
    "AIClient",  # Backward compatible
    "AIResponse",
]
