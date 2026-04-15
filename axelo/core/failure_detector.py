"""Failure detection and recovery exports."""

from axelo.detection.unified import (
    FailureDetector,
    ErrorType,
    RecoveryResult,
    RecoveryStrategy,
    detect_error,
    diagnose_failure,
)

__all__ = [
    "FailureDetector",
    "ErrorType",
    "RecoveryResult",
    "RecoveryStrategy",
    "detect_error",
    "diagnose_failure",
]
