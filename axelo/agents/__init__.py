"""
Agents Module (DEPRECATED)

This module has been moved to axelo.ai.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.agents is deprecated. "
    "Use axelo.ai instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .scanner import ScannerAgent, ScanReport
from .hypothesis import HypothesisAgent
from .codegen_agent import CodeGenAgent
from .verifier_agent import VerifierAgent, VerificationAnalysis
from .memory_writer_agent import MemoryWriterAgent

__all__ = [
    "ScannerAgent", "ScanReport",
    "HypothesisAgent",
    "CodeGenAgent",
    "VerifierAgent", "VerificationAnalysis",
    "MemoryWriterAgent",
]
