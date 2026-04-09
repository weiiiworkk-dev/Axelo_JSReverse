"""
Classifier Module (DEPRECATED)

This module has been moved to axelo.verification.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.classifier is deprecated. "
    "Use axelo.verification instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .rules import classify, DifficultyScore

__all__ = ["classify", "DifficultyScore"]
