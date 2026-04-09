"""
AI Module

Unified AI client and analysis module.
"""

from .client import AIClient
from .context_builder import ContextBuilder
from .hypothesis import AIHypothesisOutput, CodeGenOutput
from .unified import (
    # Data structures
    ModelProvider,
    ChatMessage,
    ChatResponse,
    ExecutionResult,
    # Clients
    AnthropicClient,
    DeepSeekClient,
    QwenClient,
    MultiModelAIClient,
    DualModelOrchestrator,
    # Utilities
    create_orchestrator,
    quick_chat,
)

# Task routing (kept separate)
from .task_router import (
    TaskRouter,
    TaskType,
    TaskClassification,
    PromptBuilder,
    create_router,
    quick_classify,
)

# Agents (consolidated)
from axelo.agents import (
    ScannerAgent, ScanReport,
    HypothesisAgent,
    CodeGenAgent,
    VerifierAgent, VerificationAnalysis,
    MemoryWriterAgent,
)

__all__ = [
    # Original
    "AIClient",
    "ContextBuilder", 
    "AIHypothesisOutput",
    "CodeGenOutput",
    # Unified clients
    "ModelProvider",
    "ChatMessage",
    "ChatResponse",
    "ExecutionResult",
    "AnthropicClient",
    "DeepSeekClient",
    "QwenClient",
    "MultiModelAIClient",
    "DualModelOrchestrator",
    "create_orchestrator",
    "quick_chat",
    # Task routing
    "TaskRouter",
    "TaskType",
    "TaskClassification",
    "PromptBuilder",
    "create_router",
    "quick_classify",
    # Agents
    "ScannerAgent",
    "ScanReport",
    "HypothesisAgent",
    "CodeGenAgent",
    "VerifierAgent",
    "VerificationAnalysis",
    "MemoryWriterAgent",
]