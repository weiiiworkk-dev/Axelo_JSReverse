"""
Unified Detection Module

Consolidated detection from:
- axelo/core/failure_detector.py
- axelo/detection/signature_failure.py
- axelo/detection/honeypot_detector.py

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

import structlog

log = structlog.get_logger()


# =============================================================================
# ERROR TYPES (from failure_detector.py)
# =============================================================================

class ErrorType:
    """Common error types"""
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    PARSE_ERROR = "parse_error"
    SIGNATURE_INVALID = "signature_invalid"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RecoveryStrategy:
    """A strategy for recovering from an error (from failure_detector.py)"""
    name: str
    error_types: list[str]
    apply: Callable  # Function to apply the fix
    
    description: str = ""
    success_rate: float = 0.5  # Historical success rate


@dataclass
class RecoveryResult:
    """Result of a recovery attempt (unified version)"""
    success: bool
    original_error: str = ""
    recovery_applied: str = ""
    new_code: str = ""
    confidence: float = 0.0
    suggestions: list[str] = field(default_factory=list)
    # Additional fields from signature_failure.py
    strategy: str = ""
    reason: str = ""
    requires_human: bool = False


@dataclass
class Diagnosis:
    """Diagnosis result of a failure (from signature_failure.py)"""
    indicators: dict[str, Any] = field(default_factory=dict)
    can_fix: bool = False
    recovery_priority: str = "low"
    known_pattern: str = ""
    suggested_fix: str = ""
    reason: str = ""
    
    def add_indicator(self, name: str, value: Any) -> None:
        self.indicators[name] = value
    
    @property
    def summary(self) -> str:
        return f"Diagnosis({self.reason}, fixable={self.can_fix})"


# =============================================================================
# UNIFIED FAILURE DETECTOR
# =============================================================================

class FailureDetector:
    """
    Detects failures in crawler execution.
    This is the main detector class combining functionality from multiple sources.
    """
    
    def __init__(self):
        self._error_patterns = self._build_error_patterns()
    
    def _build_error_patterns(self) -> dict:
        """Build patterns for detecting error types"""
        return {
            ErrorType.TIMEOUT: [
                r"timeout",
                r"timed out",
                r"ConnectTimeout",
                r"ReadTimeout",
            ],
            ErrorType.AUTH_ERROR: [
                r"401",
                r"403",
                r"unauthorized",
                r"forbidden",
                r"invalid.*token",
                r"invalid.*signature",
            ],
            ErrorType.RATE_LIMIT: [
                r"429",
                r"rate.*limit",
                r"too.*many.*request",
                r"throttle",
            ],
            ErrorType.PARSE_ERROR: [
                r"json.*decode",
                r"parse.*error",
                r"invalid.*json",
            ],
            ErrorType.SIGNATURE_INVALID: [
                r"signature.*invalid",
                r"sign.*error",
                r"hmac.*fail",
                r"crypto.*error",
            ],
            ErrorType.NETWORK_ERROR: [
                r"connection.*refused",
                r"connection.*reset",
                r"DNS.*error",
                r"network.*unreachable",
            ],
            ErrorType.SERVER_ERROR: [
                r"500",
                r"502",
                r"503",
                r"server.*error",
            ],
        }
    
    def detect_error_type(self, error_message: str) -> str:
        """Detect the type of error from error message"""
        error_lower = error_message.lower()
        
        for error_type, patterns in self._error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_lower, re.IGNORECASE):
                    return error_type
        
        return ErrorType.UNKNOWN
    
    def analyze_failure(self, error: str, context: Optional[dict] = None) -> Diagnosis:
        """Analyze a failure and provide diagnosis"""
        diagnosis = Diagnosis()
        
        # Detect error type
        error_type = self.detect_error_type(error)
        diagnosis.add_indicator("error_type", error_type)
        diagnosis.reason = f"Detected error type: {error_type}"
        
        # Determine if fixable
        fixable_types = [
            ErrorType.TIMEOUT,
            ErrorType.RATE_LIMIT,
            ErrorType.PARSE_ERROR,
        ]
        diagnosis.can_fix = error_type in fixable_types
        
        if diagnosis.can_fix:
            diagnosis.recovery_priority = "high"
            diagnosis.suggested_fix = f"Retry with adjusted {error_type} handling"
        
        return diagnosis
    
    def create_recovery_result(
        self,
        success: bool,
        original_error: str,
        recovery_applied: str = "",
    ) -> RecoveryResult:
        """Create a recovery result"""
        return RecoveryResult(
            success=success,
            original_error=original_error,
            recovery_applied=recovery_applied,
            confidence=0.8 if success else 0.0,
        )


# =============================================================================
# HONEY POT DETECTOR (from honeypot_detector.py)
# =============================================================================

@dataclass
class HoneypotDetectionResult:
    """Result of honeypot detection"""
    is_honeypot: bool
    confidence: float
    detected_traps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class HoneypotDetector:
    """Detects honeypot traps in target websites"""
    
    # Common honeypot indicators
    HONEYPOT_PATTERNS = {
        "hidden_fields": [
            r'hidden.*value="[a-f0-9]{32,}"',
            r'<input[^>]*type="hidden"[^>]*name="(honeypot|trap|spider|bot)"',
        ],
        "fake_links": [
            r'<a[^>]*href="[^"]*(?:trap|honeypot|spider|bot)[^"]*"',
        ],
        "decoy_forms": [
            r'<form[^>]*action="[^"]*(?:submit|trap|honeypot)[^"]*"',
        ],
        "bot_detection_scripts": [
            r'if.*\(.*bot.*\).*\{\s*window\.location',
            r'document\.body\.style\.display\s*=\s*["\']none["\']',
        ],
    }
    
    def detect(self, html_content: str) -> HoneypotDetectionResult:
        """Detect honeypot traps in HTML"""
        detected_traps = []
        
        for trap_type, patterns in self.HONEYPOT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, html_content, re.IGNORECASE):
                    detected_traps.append(trap_type)
        
        is_honeypot = len(detected_traps) > 0
        confidence = min(0.5 + len(detected_traps) * 0.15, 0.95)
        
        recommendations = []
        if is_honeypot:
            recommendations.append("Consider using advanced browser fingerprinting")
            recommendations.append("Add randomized delays between requests")
        
        return HoneypotDetectionResult(
            is_honeypot=is_honeypot,
            confidence=confidence,
            detected_traps=detected_traps,
            recommendations=recommendations,
        )


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def detect_error(error_message: str) -> str:
    """Quick helper to detect error type"""
    detector = FailureDetector()
    return detector.detect_error_type(error_message)


def diagnose_failure(error: str, context: Optional[dict] = None) -> Diagnosis:
    """Quick helper to diagnose failure"""
    detector = FailureDetector()
    return detector.analyze_failure(error, context)


def detect_honeypot(html_content: str) -> HoneypotDetectionResult:
    """Quick helper to detect honeypot"""
    detector = HoneypotDetector()
    return detector.detect(html_content)


# =============================================================================
# AUTO RECOVERY ENGINE (from core module)
# =============================================================================

class AutoRecoveryEngine:
    """
    Auto-recovery engine for fixing crawler failures.
    This is a simplified version - the full implementation is in the original module.
    """
    
    def __init__(self):
        self._failure_detector = FailureDetector()
    
    async def attempt_recovery(
        self,
        error: str,
        current_code: str,
        context: dict,
    ) -> RecoveryResult:
        """Attempt to recover from a failure"""
        # Analyze the error
        diagnosis = self._failure_detector.analyze_failure(error, context)
        
        if diagnosis.can_fix:
            # Apply fix based on diagnosis
            return RecoveryResult(
                success=True,
                original_error=error,
                recovery_applied=diagnosis.suggested_fix,
                confidence=0.7,
            )
        
        return RecoveryResult(
            success=False,
            original_error=error,
            recovery_applied="",
            confidence=0.0,
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Error types
    "ErrorType",
    # Data structures
    "RecoveryStrategy",
    "RecoveryResult",
    "Diagnosis",
    "HoneypotDetectionResult",
    # Detectors
    "FailureDetector",
    "HoneypotDetector",
    # Engine
    "AutoRecoveryEngine",
    # Utility functions
    "detect_error",
    "diagnose_failure",
    "detect_honeypot",
]