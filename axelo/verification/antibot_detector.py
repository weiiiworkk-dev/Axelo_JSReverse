"""
Anti-bot detection module for verification.

Provides utilities to identify anti-bot / anti-scraping responses
from web servers, enabling the verification system to distinguish
between genuine data issues and blocking responses.
"""

from __future__ import annotations

import re
from typing import Any

from axelo.config import settings


class AntibotDetector:
    """Detects anti-bot / anti-scraping responses from server data."""

    def __init__(
        self,
        patterns: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> None:
        """
        Initialize the anti-bot detector.
        
        Args:
            patterns: List of regex patterns to match anti-bot responses.
                     Defaults to settings.verification_antibot_patterns.
            fields: List of field names to check for anti-bot indicators.
                   Defaults to settings.verification_antibot_fields.
        """
        self.patterns = patterns or settings.verification_antibot_patterns
        self.fields = fields or settings.verification_antibot_fields
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def is_antibot_response(self, data: Any) -> tuple[bool, str]:
        """
        Check if the response data indicates an anti-bot blocking.
        
        Args:
            data: The response data to check (dict, list, or string)
            
        Returns:
            Tuple of (is_blocked, reason) where:
            - is_blocked: True if anti-bot detected, False otherwise
            - reason: Human-readable reason for the detection
        """
        if data is None:
            return False, ""
        
        # Check string responses directly
        if isinstance(data, str):
            return self._check_string(data)
        
        # Check dict responses for error fields
        if isinstance(data, dict):
            return self._check_dict(data)
        
        # Check list responses (check first element)
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                return self._check_dict(first_item)
            elif isinstance(first_item, str):
                return self._check_string(first_item)
        
        return False, ""

    def _check_string(self, text: str) -> tuple[bool, str]:
        """Check string content for anti-bot patterns."""
        for pattern in self._compiled_patterns:
            match = pattern.search(text)
            if match:
                return True, f"Anti-bot pattern matched: {match.group()}"
        return False, ""

    def _check_dict(self, data: dict) -> tuple[bool, str]:
        """Check dictionary response for anti-bot indicators."""
        # Check common error fields
        for field in self.fields:
            if field in data:
                value = data[field]
                
                # Check numeric error codes (typically 9xxxxx for Shopee, 4xx, 5xx)
                if isinstance(value, (int, float)):
                    if value >= 90000000 or (value >= 400 and value < 600):
                        return True, f"Error code detected: {value}"
                    continue
                
                # Check string error messages
                if isinstance(value, str):
                    result = self._check_string(value)
                    if result[0]:
                        return True, f"Error field '{field}': {result[1]}"
                    continue
                
                # Check boolean success field
                if isinstance(value, bool) and field.lower() == "success" and not value:
                    return True, f"Success field is false in '{field}'"
        
        return False, ""

    def get_antibot_score(self, data: Any) -> float:
        """
        Get a score indicating likelihood of anti-bot response.
        
        Args:
            data: The response data to check
            
        Returns:
            Score from 0.0 (clean) to 1.0 (definitely blocked)
        """
        is_blocked, reason = self.is_antibot_response(data)
        if is_blocked:
            return 0.9  # High confidence of blocking
        return 0.0


# Global instance for convenience
_default_detector: AntibotDetector | None = None


def get_detector() -> AntibotDetector:
    """Get the global antibot detector instance."""
    global _default_detector
    if _default_detector is None:
        _default_detector = AntibotDetector()
    return _default_detector
