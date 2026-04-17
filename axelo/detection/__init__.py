"""
Detection Module

Unified detection system for failures, honeypots, and signature issues.
"""

from .unified import (
    ErrorType,
    FailureDetector,
    RecoveryResult,
    RecoveryStrategy,
    Diagnosis,
    HoneypotDetector,
    HoneypotDetectionResult,
    HoneypotReport,
    HiddenField,
    TrapLink,
    HoneypotAwareActionRunner,
    detect_error,
    diagnose_failure,
    detect_honeypot,
)

__all__ = [
    "ErrorType",
    "FailureDetector",
    "RecoveryResult",
    "RecoveryStrategy",
    "Diagnosis",
    "HoneypotDetector",
    "HoneypotDetectionResult",
    "HoneypotReport",
    "HiddenField",
    "TrapLink",
    "HoneypotAwareActionRunner",
    "detect_error",
    "diagnose_failure",
    "detect_honeypot",
]