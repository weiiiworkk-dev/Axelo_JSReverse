"""
Cost Module (DEPRECATED)

This module has been moved to axelo.platform.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.cost is deprecated. "
    "Use axelo.platform instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .governor import CostGovernor
from .tracker import CostRecord, CostBudget

__all__ = ["CostBudget", "CostGovernor", "CostRecord"]
