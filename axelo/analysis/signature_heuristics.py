"""
Heuristic rules for signature strategy selection.

Provides rule-based detection of:
- Time-sensitive fields (timestamps, nonces that expire)
- Header时效性 (whether headers are reusable or need refresh)
- Signature complexity indicators
"""

from __future__ import annotations

import re
from typing import Any

# Pattern to detect time-related fields
TIME_SENSITIVE_PATTERNS = [
    r"_?(timestamp|time|ts)",           # timestamp, time, ts
    r"_?(nonce|nonc)",                   # nonce
    r"_?(sign|sign)",                    # signature related
    r"_?(token|tk)",                     # token
    r"_?(key|k)",                        # key (shorter for header names)
    r"_?(salt|s)",                       # salt
    r"_?(random|rand)",                 # random
    r"_?(req|request)_?id",             # request id
    r"_?(ct|client)_?time",             # client time
    r"_?(exp|expir)",                    # expiration
    r"_?(seq|sequence)",                 # sequence
]

# Pattern to detect high-entropy strings (signatures, tokens)
HIGH_ENTROPY_PATTERNS = [
    r"^[a-z0-9]{32,}$",                  # 32+ lowercase hex chars
    r"^[A-Za-z0-9+/]{40,}=$",            # Base64 string
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",  # UUID-like
]

# Header names that are typically time-sensitive
TIME_SENSITIVE_HEADERS = {
    "x-sap-sec",
    "x-sap-ri",
    "af-ac-enc-dat",
    "af-ac-enc-sz-token",
    "x-csrf-token",
    "x-request-id",
    "x-timestamp",
    "x-signature",
    "authorization",
    "x-auth-token",
}


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile regex patterns for efficiency."""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Pre-compiled patterns
_TIME_SENSITIVE_RE = compile_patterns(TIME_SENSITIVE_PATTERNS)
_HIGH_ENTROPY_RE = compile_patterns(HIGH_ENTROPY_PATTERNS)


class SignatureHeuristics:
    """Heuristic detector for signature strategy selection."""

    def __init__(
        self,
        time_patterns: list[str] | None = None,
        entropy_patterns: list[str] | None = None,
    ) -> None:
        self.time_patterns = compile_patterns(time_patterns or TIME_SENSITIVE_PATTERNS)
        self.entropy_patterns = compile_patterns(entropy_patterns or HIGH_ENTROPY_PATTERNS)

    def is_time_sensitive_field(self, field_name: str) -> bool:
        """
        Check if a field name indicates time-sensitive data.
        
        Args:
            field_name: The field name to check
            
        Returns:
            True if the field is likely time-sensitive
        """
        field_lower = field_name.lower()
        
        # Direct check against known time-sensitive headers
        if field_lower in TIME_SENSITIVE_HEADERS:
            return True
        
        # Pattern-based detection
        for pattern in self.time_patterns:
            if pattern.search(field_lower):
                return True
        
        return False

    def is_high_entropy_value(self, value: str) -> bool:
        """
        Check if a value looks like a signature/token (high entropy).
        
        Args:
            value: The value to check
            
        Returns:
            True if the value looks like a signature or token
        """
        if not value or not isinstance(value, str):
            return False
        
        value = value.strip()
        
        for pattern in self.entropy_patterns:
            if pattern.match(value):
                return True
        
        return False

    def analyze_header(
        self,
        header_name: str,
        header_value: str,
    ) -> dict[str, Any]:
        """
        Analyze a header for time sensitivity and entropy.
        
        Args:
            header_name: Name of the header
            header_value: Value of the header
            
        Returns:
            Dictionary with analysis results
        """
        is_time = self.is_time_sensitive_field(header_name)
        is_high_entropy = self.is_high_entropy_value(header_value)
        value_length = len(header_value) if header_value else 0
        
        return {
            "header_name": header_name,
            "is_time_sensitive": is_time,
            "is_high_entropy": is_high_entropy,
            "value_length": value_length,
            "likely_expires": is_time or (is_high_entropy and value_length > 100),
        }

    def get_required_strategy(self, headers: dict[str, str]) -> str:
        """
        Determine the required signature strategy based on header analysis.
        
        Args:
            headers: Dictionary of header_name -> header_value
            
        Returns:
            Strategy recommendation: "bridge" (needs live browser) or "replay" (can replay)
        """
        requires_bridge = False
        
        for name, value in headers.items():
            analysis = self.analyze_header(name, value)
            
            # If header is time-sensitive AND high-entropy, likely needs Bridge
            if analysis["is_time_sensitive"] and analysis["is_high_entropy"]:
                requires_bridge = True
                break
            
            # Very long encrypted-looking values also need Bridge
            if analysis["value_length"] > 500:
                requires_bridge = True
        
        return "bridge" if requires_bridge else "replay"

    def get_header_expiry_warnings(self, headers: dict[str, str]) -> list[str]:
        """
        Get warnings about potentially expiring headers.
        
        Args:
            headers: Dictionary of header_name -> header_value
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        for name, value in headers.items():
            analysis = self.analyze_header(name, value)
            
            if analysis["likely_expires"]:
                warnings.append(
                    f"Header '{name}' appears time-sensitive (length={analysis['value_length']}, "
                    f"time_sensitive={analysis['is_time_sensitive']}, "
                    f"high_entropy={analysis['is_high_entropy']}). "
                    "Consider using Bridge mode for live generation."
                )
        
        return warnings


# Global instance
_default_heuristics: SignatureHeuristics | None = None


def get_heuristics() -> SignatureHeuristics:
    """Get the global heuristics instance."""
    global _default_heuristics
    if _default_heuristics is None:
        _default_heuristics = SignatureHeuristics()
    return _default_heuristics
