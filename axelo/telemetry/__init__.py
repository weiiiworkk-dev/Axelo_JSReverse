"""
Telemetry Module (DEPRECATED)

This module has been moved to axelo.platform.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.telemetry is deprecated. "
    "Use axelo.platform instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .report import write_run_report

__all__ = ["write_run_report"]

