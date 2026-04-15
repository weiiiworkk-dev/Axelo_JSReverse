"""
AI Module

Unified AI client and analysis module.
"""

from .client import AIClient
from .context_builder import ContextBuilder
from .hypothesis import AIHypothesisOutput, CodeGenOutput
from .unified import (
    ModelProvider,
    ChatMessage,
    ChatResponse,
    ExecutionResult,
    DeepSeekClient,
    DeepSeekV3Client,
    MultiModelAIClient,
    DeepSeekExecutionClient,
    create_execution_client,
    quick_chat,
)

# Agents (consolidated)
from .agents import (
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
    "DeepSeekClient",
    "DeepSeekV3Client",
    "MultiModelAIClient",
    "DeepSeekExecutionClient",
    "create_execution_client",
    "quick_chat",
    # Agents
    "ScannerAgent",
    "ScanReport",
    "HypothesisAgent",
    "CodeGenAgent",
    "VerifierAgent",
    "VerificationAnalysis",
    "MemoryWriterAgent",
]
