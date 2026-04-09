"""
Failure Detection and Auto-Recovery System (DEPRECATED)

This module has been moved to axelo.detection.unified.
Please update your imports:

    from axelo.detection.unified import FailureDetector, ErrorType, detect_error

This file is kept for backward compatibility and will be removed in a future version.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

# Re-export from new location for backward compatibility
from axelo.detection.unified import (
    FailureDetector,
    ErrorType,
    RecoveryResult,
    RecoveryStrategy,
    detect_error,
    diagnose_failure,
)

warnings.warn(
    "axelo.core.failure_detector is deprecated. "
    "Use axelo.detection.unified instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    "FailureDetector",
    "ErrorType",
    "RecoveryResult",
    "RecoveryStrategy",
    "detect_error",
    "diagnose_failure",
]