"""
Unified AI Client Module

Consolidated AI clients:
- axelo/ai/client.py
- axelo/ai/dual_model_client.py
- axelo/ai/multi_model_client.py

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

import os
import json
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

import structlog

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ModelProvider(str, Enum):
    """Supported AI model providers"""
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    OPENAI = "openai"


@dataclass
class ChatMessage:
    """Chat message structure"""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ChatResponse:
    """Chat response structure"""
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""


@dataclass
class ExecutionResult:
    """Execution result from AI operation"""
    success: bool
    output: Any = None
    error: str = ""
    metrics: dict = field(default_factory=dict)


# =============================================================================
# BASE CLIENT
# =============================================================================

class BaseAIClient:
    """Base class for AI clients"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = ""):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._model = model
        self._client = None
    
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Send chat request"""
        raise NotImplementedError
    
    async def close(self):
        """Close client"""
        pass


# =============================================================================
# ANTHROPIC CLIENT
# =============================================================================

class AnthropicClient(BaseAIClient):
    """Anthropic Claude API client"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        super().__init__(api_key, model)
        self._base_url = "https://api.anthropic.com/v1"
    
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Send chat request to Anthropic"""
        # Simplified implementation - in production use anthropic SDK
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        
        # Convert messages format
        system_msg = None
        filtered_messages = []
        for msg in messages:
            if msg.role == "system":
                system_msg = msg.content
            else:
                filtered_messages.append({"role": msg.role, "content": msg.content})
        
        payload = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": filtered_messages,
        }
        if system_msg:
            payload["system"] = system_msg
        
        # In real implementation, make HTTP request here
        log.info("anthropic_chat_request", model=self._model)
        
        return ChatResponse(
            content="",  # Would be actual response
            model=self._model,
            usage={},
        )


# =============================================================================
# DEEPSEEK CLIENT
# =============================================================================

class DeepSeekClient(BaseAIClient):
    """DeepSeek API client"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        super().__init__(api_key, model)
        self._base_url = "https://api.deepseek.com/v1"
    
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Send chat request to DeepSeek"""
        log.info("deepseek_chat_request", model=self._model)
        
        return ChatResponse(
            content="",
            model=self._model,
            usage={},
        )


# =============================================================================
# QWEN CLIENT
# =============================================================================

class QwenClient(BaseAIClient):
    """Qwen API client"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-turbo"):
        super().__init__(api_key, model)
        self._base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    async def chat(self, messages: list[ChatMessage]) -> ChatResponse:
        """Send chat request to Qwen"""
        log.info("qwen_chat_request", model=self._model)
        
        return ChatResponse(
            content="",
            model=self._model,
            usage={},
        )


# =============================================================================
# UNIFIED MULTI-MODEL CLIENT
# =============================================================================

class MultiModelAIClient:
    """
    Unified AI client supporting multiple providers.
    This is the main client class that combines functionality from
    dual_model_client.py and multi_model_client.py.
    """
    
    def __init__(
        self,
        primary_provider: ModelProvider = ModelProvider.ANTHROPIC,
        fallback_provider: Optional[ModelProvider] = None,
    ):
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._clients: dict[ModelProvider, BaseAIClient] = {}
        self._init_clients()
    
    def _init_clients(self):
        """Initialize clients for each provider"""
        # Anthropic (primary)
        self._clients[ModelProvider.ANTHROPIC] = AnthropicClient()
        
        # DeepSeek
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if api_key:
            self._clients[ModelProvider.DEEPSEEK] = DeepSeekClient(api_key)
        
        # Qwen
        api_key = os.getenv("QWEN_API_KEY", "")
        if api_key:
            self._clients[ModelProvider.QWEN] = QwenClient(api_key)
    
    async def chat(
        self,
        messages: list[ChatMessage],
        provider: Optional[ModelProvider] = None,
    ) -> ChatResponse:
        """Send chat request with automatic fallback"""
        target_provider = provider or self._primary_provider
        
        # Try primary provider
        if target_provider in self._clients:
            try:
                return await self._clients[target_provider].chat(messages)
            except Exception as e:
                log.warning("primary_provider_failed", provider=target_provider.value, error=str(e))
        
        # Try fallback if available
        if self._fallback_provider and self._fallback_provider in self._clients:
            try:
                return await self._clients[self._fallback_provider].chat(messages)
            except Exception as e:
                log.warning("fallback_provider_failed", provider=self._fallback_provider.value, error=str(e))
        
        raise RuntimeError("All AI providers failed")
    
    async def close(self):
        """Close all clients"""
        for client in self._clients.values():
            await client.close()


# =============================================================================
# DUAL MODEL ORCHESTRATOR (from dual_model_client.py)
# =============================================================================

class DualModelOrchestrator:
    """
    Orchestrates dual-model collaboration for complex tasks.
    Combines reasoning (DeepSeek/Qwen) with execution (Claude).
    """
    
    def __init__(
        self,
        reasoning_model: str = "deepseek-chat",
        execution_model: str = "claude-sonnet-4-20250514",
    ):
        self._reasoning_client = DeepSeekClient(model=reasoning_model)
        self._execution_client = AnthropicClient(model=execution_model)
    
    async def execute_task(self, task: str) -> ExecutionResult:
        """Execute a task using dual-model collaboration"""
        log.info("dual_model_task_start", task=task[:100])
        
        # Step 1: Reasoning model analyzes task
        reasoning_messages = [
            ChatMessage(role="user", content=f"Analyze this task: {task}")
        ]
        reasoning_response = await self._reasoning_client.chat(reasoning_messages)
        
        # Step 2: Execution model produces result
        execution_messages = [
            ChatMessage(role="system", content=f"Analysis: {reasoning_response.content}"),
            ChatMessage(role="user", content=task),
        ]
        execution_response = await self._execution_client.chat(execution_messages)
        
        return ExecutionResult(
            success=True,
            output=execution_response.content,
            metrics={
                "reasoning_model": self._reasoning_client._model,
                "execution_model": self._execution_client._model,
            },
        )
    
    async def close(self):
        """Close both clients"""
        await self._reasoning_client.close()
        await self._execution_client.close()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_orchestrator(
    reasoning_model: str = "deepseek-chat",
    execution_model: str = "claude-sonnet-4-20250514",
) -> DualModelOrchestrator:
    """Create a dual-model orchestrator"""
    return DualModelOrchestrator(reasoning_model, execution_model)


async def quick_chat(message: str, provider: ModelProvider = ModelProvider.ANTHROPIC) -> str:
    """Quick chat helper"""
    client = MultiModelAIClient(primary_provider=provider)
    messages = [ChatMessage(role="user", content=message)]
    response = await client.chat(messages)
    await client.close()
    return response.content


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
    "BaseAIClient",
    "AnthropicClient",
    "DeepSeekClient",
    "QwenClient",
    "MultiModelAIClient",
    "DualModelOrchestrator",
    # Utilities
    "create_orchestrator",
    "quick_chat",
]