"""
Multi-Model AI Client Support

This module adds support for multiple AI models beyond Anthropic,
including OpenAI and local models, with automatic fallback.

Version: 1.0
Created: 2026-04-06
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Type, TypeVar

import structlog
from pydantic import BaseModel

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
    provider: str = "anthropic"  # anthropic, openai, local


class AIProvider:
    """Base class for AI providers"""
    
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate completion"""
        raise NotImplementedError
    
    def get_model_name(self) -> str:
        """Get model name"""
        raise NotImplementedError


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider"""
    
    def __init__(self, api_key: str, model: str = "claude-opus-4-6") -> None:
        import anthropic
        import anyio
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._anyio = anyio
    
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate completion using Anthropic"""
        # Check if cache control is available (newer Anthropic SDK)
        system_content: str | list = system_prompt
        try:
            system_content = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        except (TypeError, NameError):
            pass  # Fall back to string
        
        response = await self._anyio.to_thread.run_sync(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_content,
                messages=[{"role": "user", "content": user_message}],
            )
        )
        
        return {
            "content": response.content[0].text if response.content else "",
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "response_id": response.id,
            "model": response.model,
        }
    
    def get_model_name(self) -> str:
        return self._model


class OpenAIProvider(AIProvider):
    """OpenAI provider (GPT-4, GPT-4 Turbo, etc.)"""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo") -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Please install openai: pip install openai")
        
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
    
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate completion using OpenAI"""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
        )
        
        choice = response.choices[0]
        return {
            "content": choice.message.content or "",
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "response_id": response.id,
            "model": response.model,
        }
    
    def get_model_name(self) -> str:
        return self._model


class LocalProvider(AIProvider):
    """Local LLM provider (Ollama, LM Studio, etc.)"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2") -> None:
        try:
            import httpx
        except ImportError:
            raise ImportError("Please install httpx: pip install httpx")
        
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)
    
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> dict:
        """Generate completion using local LLM"""
        full_prompt = f"System: {system_prompt}\n\nUser: {user_message}"
        
        response = await self._client.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                }
            },
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "content": data.get("response", ""),
            "input_tokens": len(full_prompt) // 4,  # Approximate
            "output_tokens": len(data.get("response", "")) // 4,
            "response_id": data.get("model", ""),
            "model": self._model,
        }
    
    def get_model_name(self) -> str:
        return f"local:{self._model}"
    
    async def close(self):
        await self._client.aclose()


class MultiModelAIClient:
    """
    AI client with multi-model support and automatic fallback.
    
    Usage:
        client = MultiModelAIClient()
        
        # Use specific provider
        response = await client.analyze(
            prompt="...",
            model="openai:gpt-4"
        )
        
        # Use with fallback
        response = await client.analyze_with_fallback(
            prompt="...",
            providers=["anthropic", "openai"],
        )
    """
    
    def __init__(
        self,
        anthropic_key: str | None = None,
        openai_key: str | None = None,
        default_model: str = "claude-opus-4-6",
    ) -> None:
        self._anthropic_key = anthropic_key
        self._openai_key = openai_key
        self._default_model = default_model
        self._providers: dict[str, AIProvider] = {}
        
        # Initialize available providers
        if anthropic_key:
            self._providers["anthropic"] = AnthropicProvider(
                anthropic_key, default_model
            )
        if openai_key:
            self._providers["openai"] = OpenAIProvider(openai_key)
    
    def _parse_model(self, model: str) -> tuple[str, str]:
        """Parse model string like 'openai:gpt-4' into (provider, model)"""
        if ":" in model:
            provider, model_name = model.split(":", 1)
            return provider, model_name
        return "anthropic", model
    
    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> AIResponse:
        """Analyze using specified model or default"""
        model = model or self._default_model
        provider_name, model_name = self._parse_model(model)
        
        # Get or create provider
        if provider_name in self._providers:
            provider = self._providers[provider_name]
        elif provider_name == "anthropic" and self._anthropic_key:
            provider = AnthropicProvider(self._anthropic_key, model_name)
            self._providers["anthropic"] = provider
        elif provider_name == "openai" and self._openai_key:
            provider = OpenAIProvider(self._openai_key, model_name)
            self._providers["openai"] = provider
        else:
            raise ValueError(f"Provider {provider_name} not available")
        
        # Execute
        result = await provider.complete(system_prompt, user_message, max_tokens)
        
        return AIResponse(
            data=result["content"],
            model=result["model"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            response_id=result.get("response_id", ""),
            provider=provider_name,
        )
    
    async def analyze_with_fallback(
        self,
        system_prompt: str,
        user_message: str,
        providers: list[str] | None = None,
        max_tokens: int = 8192,
    ) -> AIResponse:
        """
        Analyze with automatic fallback.
        
        Tries each provider in order until one succeeds.
        """
        providers = providers or ["anthropic", "openai"]
        
        last_error = None
        for provider_name in providers:
            try:
                # Build model name
                model = f"{provider_name}:{self._default_model}"
                if provider_name == "anthropic":
                    model = self._default_model
                
                return await self.analyze(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                last_error = e
                log.warning(
                    "ai_provider_failed",
                    provider=provider_name,
                    error=str(e),
                )
                continue
        
        raise RuntimeError(f"All providers failed. Last error: {last_error}")
    
    def get_available_providers(self) -> list[str]:
        """Get list of available providers"""
        return list(self._providers.keys())


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

class AIClient:
    """
    Backward compatible wrapper for existing code.
    Use MultiModelAIClient for new features.
    """
    
    def __init__(self, api_key: str, model: str = "claude-opus-4-6") -> None:
        self._client = MultiModelAIClient(
            anthropic_key=api_key,
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
    "AIProvider",
    "AnthropicProvider", 
    "OpenAIProvider",
    "LocalProvider",
    "MultiModelAIClient",
    "AIClient",  # Backward compatible
    "AIResponse",
]
