"""
Generic Signature Pattern Library

A site-agnostic database of common signature/encryption patterns.
This library intentionally avoids any brand/domain-specific tuning.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignaturePattern:
    """Known signature pattern"""
    id: str
    name: str
    scope: str
    algorithm: str  # hmac-sha256, md5, etc.
    key_source: str  # static, dynamic, cookie, etc.
    key_location: str  # Where the key comes from
    parameter_order: list[str]  # Order of parameters in signature
    header_name: str  # Where signature is placed
    notes: str = ""
    confidence: float = 1.0  # How confident we are in this pattern


# =============================================================================
# KNOWN PATTERNS DATABASE
# =============================================================================

KNOWN_PATTERNS: list[SignaturePattern] = [
    SignaturePattern(
        id="generic_hmac_sha256",
        name="Generic HMAC-SHA256",
        scope="universal",
        algorithm="hmac-sha256",
        key_source="unknown",
        key_location="unknown",
        parameter_order=["key", "timestamp", "nonce"],
        header_name="X-Sign",
        notes="Common HMAC-SHA256 pattern - needs manual analysis",
        confidence=0.5,
    ),
    SignaturePattern(
        id="generic_md5",
        name="Generic MD5 Hash",
        scope="universal",
        algorithm="md5",
        key_source="unknown",
        key_location="unknown",
        parameter_order=["data"],
        header_name="X-Md5",
        notes="Common MD5 pattern - needs manual analysis",
        confidence=0.5,
    ),
    SignaturePattern(
        id="generic_aes_payload",
        name="Generic AES Payload Encryption",
        scope="universal",
        algorithm="aes-cbc",
        key_source="dynamic",
        key_location="runtime memory / bootstrap response",
        parameter_order=["payload", "iv", "timestamp"],
        header_name="X-Encrypted",
        notes="Common encrypted-payload pattern in browser APIs",
        confidence=0.55,
    ),
    SignaturePattern(
        id="generic_rsa_sign",
        name="Generic RSA Request Signature",
        scope="universal",
        algorithm="rsa-sha256",
        key_source="static",
        key_location="bundle config / env",
        parameter_order=["method", "path", "timestamp", "body_hash"],
        header_name="Authorization",
        notes="Common asymmetric signing shape in protected APIs",
        confidence=0.6,
    ),
]


# =============================================================================
# PATTERN MATCHING
# =============================================================================

class PatternMatcher:
    """Match known patterns against new targets"""
    
    def __init__(self):
        self.patterns = KNOWN_PATTERNS
    
    def match_by_scope(self, scope: str = "universal") -> list[SignaturePattern]:
        """Find patterns matching a generic scope"""
        return [p for p in self.patterns if scope in p.scope or p.scope == "universal"]
    
    def match_by_algorithm(self, algorithm: str) -> list[SignaturePattern]:
        """Find patterns by algorithm"""
        return [p for p in self.patterns if algorithm in p.algorithm]
    
    def match_by_key_source(self, key_source: str) -> list[SignaturePattern]:
        """Find patterns by key source"""
        return [p for p in self.patterns if key_source in p.key_source]
    
    def suggest_pattern(self, scope: str = "universal", algorithm: str = None) -> Optional[SignaturePattern]:
        """Suggest most likely generic pattern"""
        candidates = self.match_by_scope(scope)
        
        if not candidates:
            return None
        
        if algorithm:
            candidates = [c for c in candidates if algorithm in c.algorithm]
        
        if not candidates:
            return None
        
        # Return highest confidence
        return max(candidates, key=lambda p: p.confidence)
    
    def add_pattern(self, pattern: SignaturePattern) -> None:
        """Add a new pattern to the library"""
        self.patterns.append(pattern)
    
    def get_all_patterns(self) -> list[SignaturePattern]:
        """Get all patterns"""
        return self.patterns.copy()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SignaturePattern",
    "KNOWN_PATTERNS",
    "PatternMatcher",
]
