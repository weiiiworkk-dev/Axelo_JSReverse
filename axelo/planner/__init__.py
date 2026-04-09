"""
Planner Module (DEPRECATED)

This module has been moved to axelo.core.engine.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.planner is deprecated. "
    "Use axelo.core.engine instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .strategy import Planner, PlanDecision

__all__ = ["PlanDecision", "Planner"]

