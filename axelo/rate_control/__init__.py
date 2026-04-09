"""
Rate Control Module (DEPRECATED)

This module has been moved to axelo.platform.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.rate_control is deprecated. "
    "Use axelo.platform instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .adaptive_limiter import (
    DomainHistory,
    PacingStrategy,
    PacingModel,
    AdaptiveRateController,
    StrategySelector,
)

__all__ = [
    "DomainHistory",
    "PacingStrategy",
    "PacingModel",
    "AdaptiveRateController",
    "StrategySelector",
]