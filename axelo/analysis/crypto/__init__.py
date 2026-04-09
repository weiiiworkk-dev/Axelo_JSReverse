"""
Unified Crypto Analysis Module

Consolidated crypto detection and analysis from:
- axelo/core/crypto_detector.py
- axelo/analysis/static/crypto_patterns.py

This module provides comprehensive crypto algorithm detection,
pattern matching, and analysis for JavaScript reverse engineering.

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import structlog

log = structlog.get_logger()


# =============================================================================
# CRYPTO TYPES
# =============================================================================

class CryptoType(str, Enum):
    """Types of cryptographic operations"""
    HASH = "hash"
    HMAC = "hmac"
    ENCRYPTION = "encryption"  # Symmetric
    SIGNATURE = "signature"    # Asymmetric
    ENCODING = "encoding"     # Base64, Hex, etc.
    KEY_DERIVATION = "key_derivation"
    RANDOM = "random"         # Random number generation
    UNKNOWN = "unknown"


class CryptoAlgorithm(str, Enum):
    """Specific crypto algorithms"""
    # Hash
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA512 = "sha512"
    SHA3 = "sha3"
    BLAKE2 = "blake2"
    
    # HMAC variants
    HMAC_MD5 = "hmac_md5"
    HMAC_SHA1 = "hmac_sha1"
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"
    
    # Encryption
    AES_CBC = "aes_cbc"
    AES_GCM = "aes_gcm"
    AES_CTR = "aes_ctr"
    AES_ECB = "aes_ecb"
    
    # RSA
    RSA_PKCS1 = "rsa_pkcs1"
    RSA_OAEP = "rsa_oaep"
    RSA_PSS = "rsa_pss"
    
    # Encoding
    BASE64 = "base64"
    HEX = "hex"
    URL = "url"
    
    # Unknown
    UNKNOWN = "unknown"


# =============================================================================
# DATA STRUCTURES (from crypto_detector.py)
# =============================================================================

@dataclass
class CryptoOperation:
    """A detected cryptographic operation"""
    algorithm: CryptoAlgorithm
    crypto_type: CryptoType
    
    # Code location
    code_snippet: str
    line_number: int
    
    # Context
    library: Optional[str] = None  # CryptoJS, Node crypto, etc.
    parameters: list[str] = field(default_factory=list)  # Key, data, mode, etc.
    confidence: float = 0.0
    
    # Additional info
    variant: Optional[str] = None  # e.g., "hmac-sha256"


@dataclass
class KeySource:
    """Information about key source"""
    source_type: str  # static, dynamic, cookie, etc.
    location: str     # Where to find it
    extraction_method: Optional[str] = None
    
    # Key value (if static)
    value: Optional[str] = None


@dataclass
class CryptoAnalysis:
    """Complete crypto analysis result"""
    operations: list[CryptoOperation] = field(default_factory=list)
    key_sources: list[KeySource] = field(default_factory=list)
    likely_algorithms: list[tuple[CryptoAlgorithm, float]] = field(default_factory=list)
    overall_confidence: float = 0.0
    
    # Summary
    has_hmac: bool = False
    has_aes: bool = False
    has_rsa: bool = False
    has_custom: bool = False
    
    def to_dict(self) -> dict:
        return {
            "operations": [
                {
                    "algorithm": op.algorithm.value,
                    "type": op.crypto_type.value,
                    "confidence": op.confidence,
                }
                for op in self.operations
            ],
            "algorithms": [(a.value, c) for a, c in self.likely_algorithms],
            "confidence": self.overall_confidence,
        }


# =============================================================================
# CRYPTO PATTERN DEFINITIONS (from crypto_patterns.py)
# =============================================================================

@dataclass
class CryptoPattern:
    """Crypto algorithm pattern definition"""
    name: str
    aliases: list[str]
    patterns: list[str]
    requires_key: bool = False
    mode: Optional[str] = None  # CBC, GCM, ECB, CTR, etc.
    encoding: Optional[str] = None  # base64, hex, utf8, etc.


class CryptoPatterns:
    """
    Comprehensive crypto detection patterns
    """
    
    # Library signatures
    LIBRARIES = {
        "crypto-js": [
            "CryptoJS",
            "CryptoJS.AES",
            "CryptoJS.HmacSHA256",
            "CryptoJS.MD5",
        ],
        "node-crypto": [
            "require('crypto')",
            "createHash",
            "createHmac",
            "createCipher",
        ],
        "web-crypto": [
            "crypto.subtle",
            "window.crypto.subtle",
            "SubtleCrypto",
        ],
        "spark-md5": [
            "SparkMD5",
        ],
        "jsrsasign": [
            "KJUR",
            "RSA",
        ],
    }
    
    # Hash function patterns (from crypto_detector.py)
    HASH_PATTERNS = {
        CryptoAlgorithm.MD5: [
            r"md5\s*\(",
            r"\.md5\s*\(",
            r"createHash\s*\(\s*['\"]md5['\"]",
            r"CryptoJS\.MD5",
        ],
        CryptoAlgorithm.SHA1: [
            r"sha1\s*\(",
            r"\.sha1\s*\(",
            r"createHash\s*\(\s*['\"]sha1['\"]",
            r"CryptoJS\.SHA1",
        ],
        CryptoAlgorithm.SHA256: [
            r"sha256\s*\(",
            r"\.sha256\s*\(",
            r"createHash\s*\(\s*['\"]sha256['\"]",
            r"CryptoJS\.SHA256",
        ],
        CryptoAlgorithm.SHA512: [
            r"sha512\s*\(",
            r"\.sha512\s*\(",
            r"createHash\s*\(\s*['\"]sha512['\"]",
            r"CryptoJS\.SHA512",
        ],
    }
    
    # HMAC patterns
    HMAC_PATTERNS = {
        CryptoAlgorithm.HMAC_MD5: [
            r"createHmac\s*\(\s*['\"]md5['\"]",
            r"HmacMD5",
        ],
        CryptoAlgorithm.HMAC_SHA1: [
            r"createHmac\s*\(\s*['\"]sha1['\"]",
            r"HmacSHA1",
        ],
        CryptoAlgorithm.HMAC_SHA256: [
            r"createHmac\s*\(\s*['\"]sha256['\"]",
            r"HmacSHA256",
        ],
        CryptoAlgorithm.HMAC_SHA512: [
            r"createHmac\s*\(\s*['\"]sha512['\"]",
            r"HmacSHA512",
        ],
    }
    
    # AES patterns
    AES_PATTERNS = {
        CryptoAlgorithm.AES_CBC: [
            r"AES.*CBC",
            r"mode.*CBC",
            r"createCipheriv\s*\(\s*['\"]aes-.*cbc['\"]",
        ],
        CryptoAlgorithm.AES_GCM: [
            r"AES.*GCM",
            r"mode.*GCM",
        ],
        CryptoAlgorithm.AES_CTR: [
            r"AES.*CTR",
            r"mode.*CTR",
        ],
        CryptoAlgorithm.AES_ECB: [
            r"AES.*ECB",
            r"mode.*ECB",
        ],
    }
    
    # RSA patterns
    RSA_PATTERNS = {
        CryptoAlgorithm.RSA_PKCS1: [
            r"RSA.*encrypt.*pkcs1",
            r"sign.*RSA.*PKCS1",
            r"rsa.*sign",
        ],
        CryptoAlgorithm.RSA_OAEP: [
            r"RSA.*encrypt.*oaep",
            r"RSA-OAEP",
        ],
        CryptoAlgorithm.RSA_PSS: [
            r"RSA.*sign.*pss",
            r"RSA-PSS",
        ],
    }
    
    # Encoding patterns
    ENCODING_PATTERNS = {
        CryptoAlgorithm.BASE64: [
            r"btoa\s*\(",
            r"atob\s*\(",
            r"\.toBase64\(",
            r"\.fromBase64\(",
            r"CryptoJS\.enc\.Base64",
        ],
        CryptoAlgorithm.HEX: [
            r"\.toHex\s*\(",
            r"\.toString\(16\)",
            r"Number.*toString\(16\)",
        ],
    }
    
    # Key source patterns
    KEY_PATTERNS = {
        "static": [
            r"['\"][0-9a-fA-F]{16,}['\"]",  # Hex key
            r"['\"][A-Za-z0-9+/]{8,}={0,2}['\"]",  # Base64 key
            r"key\s*=\s*['\"]",
            r"secret\s*=\s*['\"]",
            r"appKey\s*=\s*['\"]",
            r"appSecret\s*=\s*['\"]",
        ],
        "dynamic_cookie": [
            r"document\.cookie",
            r"Cookie\.get",
            r"\.getCookie",
        ],
        "dynamic_header": [
            r"headers\[['\"]",
            r"response\.headers",
        ],
        "dynamic_response": [
            r"\.then.*response",
            r"\.then.*data",
            r"JSON\.parse.*data",
        ],
    }
    
    # Random/generation patterns
    RANDOM_PATTERNS = [
        r"Math\.random\s*\(",
        r"crypto\.getRandomValues\s*\(",
        r"UUID\s*\(",
        r"\.uuid\s*\(",
        r"Date\.now\s*\(",
        r"performance\.now\s*\(",
    ]
    
    # Extended patterns from crypto_patterns.py
    HASH_PATTERNS_EXTENDED = {
        "md5": CryptoPattern(
            name="MD5",
            aliases=["md5", "MD5", "Message-Digest algorithm 5"],
            patterns=[
                r"\bmd5\s*\(",
                r"\.md5\s*\(",
                r"CryptoJS\.MD5",
                r"createHash\s*\(\s*['\"]md5['\"]",
                r"Crypto\.createHash\s*\(\s*['\"]md5['\"]",
                r"require\s*\(\s*['\"]crypto['\"]\)\.createHash\s*\(\s*['\"]md5['\"]",
                r"spark\.md5",
                r"blueimp-md5",
                r"js-md5",
            ],
        ),
        "sha1": CryptoPattern(
            name="SHA-1",
            aliases=["sha1", "SHA1", "sha-1", "Secure Hash Algorithm 1"],
            patterns=[
                r"\bsha1\s*\(",
                r"\.sha1\s*\(",
                r"CryptoJS\.SHA1",
                r"createHash\s*\(\s*['\"]sha1['\"]",
            ],
        ),
        "sha256": CryptoPattern(
            name="SHA-256",
            aliases=["sha256", "SHA256", "sha-256"],
            patterns=[
                r"\bsha256\s*\(",
                r"\.sha256\s*\(",
                r"CryptoJS\.SHA256",
                r"createHash\s*\(\s*['\"]sha256['\"]",
            ],
        ),
    }


# =============================================================================
# UNIFIED CRYPTO DETECTOR
# =============================================================================

class UniversalCryptoDetector:
    """
    Universal Crypto Detector
    
    Detects any cryptographic operation in JavaScript code.
    This is the main detector class that combines functionality
    from both crypto_detector.py and crypto_patterns.py.
    """
    
    def __init__(self):
        self.patterns = CryptoPatterns()
    
    def detect(self, js_code: str) -> CryptoAnalysis:
        """
        Detect all cryptographic operations in JavaScript code
        
        Args:
            js_code: JavaScript source code
            
        Returns:
            CryptoAnalysis with detected operations
        """
        operations = []
        
        # Detect operations
        operations.extend(self._detect_hashes(js_code))
        operations.extend(self._detect_hmac(js_code))
        operations.extend(self._detect_aes(js_code))
        operations.extend(self._detect_rsa(js_code))
        operations.extend(self._detect_encoding(js_code))
        operations.extend(self._detect_random(js_code))
        
        # Detect key sources
        key_sources = self._detect_key_sources(js_code)
        
        # Determine likely algorithms
        likely_algorithms = self._determine_likely_algorithms(operations)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(operations, likely_algorithms)
        
        # Build analysis
        analysis = CryptoAnalysis(
            operations=operations,
            key_sources=key_sources,
            likely_algorithms=likely_algorithms,
            overall_confidence=confidence,
            has_hmac=any(op.crypto_type == CryptoType.HMAC for op in operations),
            has_aes=any(op.algorithm in [CryptoAlgorithm.AES_CBC, CryptoAlgorithm.AES_GCM, CryptoAlgorithm.AES_CTR] for op in operations),
            has_rsa=any(op.crypto_type == CryptoType.SIGNATURE for op in operations),
            has_custom=self._has_custom_crypto(js_code),
        )
        
        log.info("crypto_analysis_complete",
                  operations=len(operations),
                  confidence=confidence)
        
        return analysis
    
    def _detect_hashes(self, js_code: str) -> list[CryptoOperation]:
        """Detect hash functions"""
        operations = []
        
        for algorithm, patterns in self.patterns.HASH_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    context = self._get_context(js_code, match.start())
                    
                    operations.append(CryptoOperation(
                        algorithm=algorithm,
                        crypto_type=CryptoType.HASH,
                        code_snippet=context,
                        line_number=js_code[:match.start()].count("\n") + 1,
                        confidence=0.9 if len(matches) > 1 else 0.7,
                        library=self._detect_library(context),
                    ))
        
        return operations
    
    def _detect_hmac(self, js_code: str) -> list[CryptoOperation]:
        """Detect HMAC operations"""
        operations = []
        
        for algorithm, patterns in self.patterns.HMAC_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    context = self._get_context(js_code, match.start())
                    
                    operations.append(CryptoOperation(
                        algorithm=algorithm,
                        crypto_type=CryptoType.HMAC,
                        code_snippet=context,
                        line_number=js_code[:match.start()].count("\n") + 1,
                        confidence=0.95 if len(matches) > 1 else 0.8,
                        library=self._detect_library(context),
                        variant=algorithm.value,
                    ))
        
        return operations
    
    def _detect_aes(self, js_code: str) -> list[CryptoOperation]:
        """Detect AES operations"""
        operations = []
        
        for algorithm, patterns in self.patterns.AES_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    context = self._get_context(js_code, match.start())
                    
                    operations.append(CryptoOperation(
                        algorithm=algorithm,
                        crypto_type=CryptoType.ENCRYPTION,
                        code_snippet=context,
                        line_number=js_code[:match.start()].count("\n") + 1,
                        confidence=0.85,
                        library=self._detect_library(context),
                    ))
        
        # Also check for generic AES
        generic_pattern = r"AES\.encrypt|CryptoJS\.AES|createCipher"
        if re.search(generic_pattern, js_code, re.IGNORECASE):
            # Already detected specific mode, skip
            pass
        
        return operations
    
    def _detect_rsa(self, js_code: str) -> list[CryptoOperation]:
        """Detect RSA operations"""
        operations = []
        
        for algorithm, patterns in self.patterns.RSA_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    context = self._get_context(js_code, match.start())
                    
                    operations.append(CryptoOperation(
                        algorithm=algorithm,
                        crypto_type=CryptoType.SIGNATURE,
                        code_snippet=context,
                        line_number=js_code[:match.start()].count("\n") + 1,
                        confidence=0.85,
                        library=self._detect_library(context),
                    ))
        
        return operations
    
    def _detect_encoding(self, js_code: str) -> list[CryptoOperation]:
        """Detect encoding operations"""
        operations = []
        
        for algorithm, patterns in self.patterns.ENCODING_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    context = self._get_context(js_code, match.start())
                    
                    operations.append(CryptoOperation(
                        algorithm=algorithm,
                        crypto_type=CryptoType.ENCODING,
                        code_snippet=context[:100],  # Truncate
                        line_number=js_code[:match.start()].count("\n") + 1,
                        confidence=0.9,
                    ))
        
        return operations
    
    def _detect_random(self, js_code: str) -> list[CryptoOperation]:
        """Detect random number generation"""
        operations = []
        
        for pattern in self.patterns.RANDOM_PATTERNS:
            matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
            for match in matches:
                context = self._get_context(js_code, match.start())
                
                operations.append(CryptoOperation(
                    algorithm=CryptoAlgorithm.UNKNOWN,
                    crypto_type=CryptoType.RANDOM,
                    code_snippet=context[:50],
                    line_number=js_code[:match.start()].count("\n") + 1,
                    confidence=0.8,
                ))
        
        return operations
    
    def _detect_key_sources(self, js_code: str) -> list[KeySource]:
        """Detect key sources"""
        sources = []
        
        for source_type, patterns in self.patterns.KEY_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                if matches:
                    sources.append(KeySource(
                        source_type=source_type,
                        location=f"pattern: {pattern[:30]}",
                    ))
        
        return sources
    
    def _determine_likely_algorithms(self, operations: list[CryptoOperation]) -> list[tuple[CryptoAlgorithm, float]]:
        """Determine likely algorithms based on operations"""
        algorithm_counts = {}
        
        for op in operations:
            if op.algorithm not in algorithm_counts:
                algorithm_counts[op.algorithm] = {"count": 0, "total_confidence": 0}
            
            algorithm_counts[op.algorithm]["count"] += 1
            algorithm_counts[op.algorithm]["total_confidence"] += op.confidence
        
        # Calculate average confidence and sort
        likely = []
        for algo, data in algorithm_counts.items():
            avg_conf = data["total_confidence"] / data["count"] if data["count"] > 0 else 0
            likely.append((algo, avg_conf))
        
        likely.sort(key=lambda x: x[1], reverse=True)
        
        return likely
    
    def _calculate_confidence(self, operations: list[CryptoOperation], likely: list) -> float:
        """Calculate overall confidence"""
        if not operations:
            return 0.0
        
        if not likely:
            return 0.3  # Low confidence if can't determine
        
        # Use highest confidence algorithm
        return likely[0][1] if likely else 0.3
    
    def _has_custom_crypto(self, js_code: str) -> bool:
        """Check for custom/obfuscated crypto"""
        custom_patterns = [
            r"function\s+sign",
            r"function\s+encrypt",
            r"\.sign\s*=\s*function",
            r"\.encrypt\s*=\s*function",
        ]
        
        for pattern in custom_patterns:
            if re.search(pattern, js_code, re.IGNORECASE):
                return True
        
        return False
    
    def _get_context(self, code: str, position: int, context_size: int = 100) -> str:
        """Get surrounding context"""
        start = max(0, position - 50)
        end = min(len(code), position + context_size)
        return code[start:end].replace("\n", " ")
    
    def _detect_library(self, context: str) -> Optional[str]:
        """Detect which crypto library is used"""
        for library, signatures in self.patterns.LIBRARIES.items():
            for sig in signatures:
                if sig.lower() in context.lower():
                    return library
        return None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def detect_crypto(js_code: str) -> CryptoAnalysis:
    """Quick helper to detect crypto in JS code"""
    detector = UniversalCryptoDetector()
    return detector.detect(js_code)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Crypto types
    "CryptoType",
    "CryptoAlgorithm",
    # Data structures
    "CryptoOperation",
    "KeySource",
    "CryptoAnalysis",
    "CryptoPattern",
    # Detector
    "CryptoPatterns",
    "UniversalCryptoDetector",
    "detect_crypto",
]