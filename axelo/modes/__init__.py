"""
Modes Module (DEPRECATED)

This module has been moved to axelo.app.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.modes is deprecated. "
    "Use axelo.app instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .base import ModeController
from .interactive import InteractiveMode
from .full_auto import AutoMode
from .full_manual import ManualMode
from .registry import create_mode, available_modes

__all__ = ["ModeController", "InteractiveMode", "AutoMode", "ManualMode", "create_mode", "available_modes"]
