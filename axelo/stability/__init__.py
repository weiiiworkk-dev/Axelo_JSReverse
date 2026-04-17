"""Stability, recovery, and human-like interaction helpers."""

from axelo.behavior.mouse_simulator import (
    MouseMovementSimulator,
    KeyboardSimulator,
    ScrollSimulator,
    IdlePatternGenerator,
    create_behavior_simulator,
)

from axelo.detection.unified import (
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
