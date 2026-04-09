"""
Policies Module (DEPRECATED)

This module has been moved to axelo.core.engine.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.policies is deprecated. "
    "Use axelo.core.engine instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .runtime import RuntimePolicy, resolve_runtime_policy

__all__ = ["RuntimePolicy", "resolve_runtime_policy"]

