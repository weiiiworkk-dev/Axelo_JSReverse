"""
Signature failure detector and auto-recovery system (DEPRECATED)

This module has been moved to axelo.detection.unified.
Please update your imports:

    from axelo.detection.unified import Diagnosis, RecoveryResult, RecoveryStrategy

This file is kept for backward compatibility and will be removed in a future version.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings
import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

warnings.warn(
    "axelo.detection.signature_failure is deprecated. "
    "Use axelo.detection.unified instead.",
    DeprecationWarning,
    stacklevel=2
)


# =============================================================================
# RE-EXPORT FROM UNIFIED MODULE
# =============================================================================

from axelo.detection.unified import (
    Diagnosis,
    RecoveryResult,
    RecoveryStrategy,
    FailureDetector,
)


# =============================================================================
# REMAINING FUNCTIONALITY (re-exported)
# =============================================================================

# Re-export the classes for backward compatibility
__all__ = [
    "Diagnosis",
    "RecoveryResult",
    "RecoveryStrategy",
    "FailureDetector",
]