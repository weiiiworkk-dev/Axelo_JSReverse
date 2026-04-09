"""
Stability Module (DEPRECATED)

This module has been moved to axelo.platform.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.stability is deprecated. "
    "Use axelo.platform instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from original locations for backward compatibility
from axelo.behavior.mouse_simulator import (
    MouseMovementSimulator,
    KeyboardSimulator,
    ScrollSimulator,
    IdlePatternGenerator,
    create_behavior_simulator,
)

from axelo.detection.honeypot_detector import (
    HoneypotDetector,
    HoneypotReport,
    HoneypotAwareActionRunner,
)

# Signature failure re-exported from unified
from axelo.detection.unified import (
    RecoveryResult,
    Diagnosis,
    RecoveryStrategy,
)

from axelo.detection.unified import (
    FailureDetector,
    ErrorType,
    detect_error,
    diagnose_failure,
)

from axelo.verification.antibot_detector import AntibotDetector

__all__ = [
    # Mouse simulator
    "MouseMovementSimulator",
    "KeyboardSimulator",
    "ScrollSimulator",
    "IdlePatternGenerator",
    "create_behavior_simulator",
    # Honeypot
    "HoneypotDetector",
    "HoneypotReport",
    "HoneypotAwareActionRunner",
    # Unified detection
    "FailureDetector",
    "ErrorType",
    "detect_error",
    "diagnose_failure",
    "RecoveryResult",
    "Diagnosis",
    # Antibot
    "AntibotDetector",
]