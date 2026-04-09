"""DeepSeek-only unified AI abstractions."""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from enum import Enum

from .dual_model_client import (
    ChatMessage,
    ChatResponse,
    ExecutionResult,
    DeepSeekClient,
    DeepSeekV3Client,
    DualModelOrchestrator,
    create_orchestrator,
    quick_chat,
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ModelProvider(str, Enum):
    """Supported provider set."""
    DEEPSEEK = "deepseek"
class MultiModelAIClient:
    """Compatibility wrapper for DeepSeek provider selection."""

    def __init__(self, primary_provider: ModelProvider = ModelProvider.DEEPSEEK, fallback_provider: ModelProvider | None = None):
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider

    async def chat(self, messages: list[ChatMessage], provider: ModelProvider | None = None) -> ChatResponse:
        _ = provider or self._primary_provider
        client = DeepSeekV3Client()
        return client.chat(messages)

    async def close(self):
        return None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Data structures
    "ModelProvider",
    "ChatMessage",
    "ChatResponse",
    "ExecutionResult",
    # Clients
    "DeepSeekClient",
    "DeepSeekV3Client",
    "MultiModelAIClient",
    "DualModelOrchestrator",
    # Utilities
    "create_orchestrator",
    "quick_chat",
]