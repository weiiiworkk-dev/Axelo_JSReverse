"""
Memory Module (DEPRECATED)

This module has been moved to axelo.models.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.memory is deprecated. "
    "Use axelo.models instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .db import MemoryDB
from .vector_store import VectorStore
from .retriever import MemoryRetriever
from .writer import MemoryWriter

__all__ = ["MemoryDB", "VectorStore", "MemoryRetriever", "MemoryWriter"]
