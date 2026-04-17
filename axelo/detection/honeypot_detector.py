"""Backward-compatibility shim — import from axelo.detection.unified directly.
This file is deprecated and will be removed in a future version.
"""
from axelo.detection.unified import (  # noqa: F401
    HoneypotDetector,
    HoneypotReport,
    HiddenField,
    TrapLink,
    HoneypotDetectionResult,
    HoneypotAwareActionRunner,
    detect_honeypot,
)

__all__ = [
    "HoneypotDetector",
    "HoneypotReport",
    "HiddenField",
    "TrapLink",
    "HoneypotDetectionResult",
    "HoneypotAwareActionRunner",
    "detect_honeypot",
]
