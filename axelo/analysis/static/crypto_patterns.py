"""Extended crypto pattern database and helper exports."""

import re
from typing import Optional

# Re-export from new location for backward compatibility
from axelo.analysis.crypto import (
    CryptoPattern as _CryptoPattern,
    CryptoPatterns as _CryptoPatterns,
    CryptoType,
    CryptoAlgorithm,
    CryptoOperation,
    CryptoAnalysis,
    UniversalCryptoDetector,
)

# Re-export the pattern classes.
CryptoPattern = _CryptoPattern
CryptoPatterns = _CryptoPatterns


# =============================================================================
# PATTERNS FROM ORIGINAL MODULE (re-created for compatibility)
# =============================================================================

HASH_PATTERNS = {
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
            r"Crypto\.createHash\s*\(\s*['\"]sha1['\"]",
        ],
    ),
    "sha256": CryptoPattern(
        name="SHA-256",
        aliases=["sha256", "SHA256", "sha-256", "SHA2"],
        patterns=[
            r"\bsha256\s*\(",
            r"\.sha256\s*\(",
            r"CryptoJS\.SHA256",
            r"createHash\s*\(\s*['\"]sha256['\"]",
            r"Crypto\.createHash\s*\(\s*['\"]sha256['\"]",
            r"sha2\s*\(",
            r"\.sha2\s*\(",
        ],
    ),
    "sha512": CryptoPattern(
        name="SHA-512",
        aliases=["sha512", "SHA512", "sha-512"],
        patterns=[
            r"\bsha512\s*\(",
            r"\.sha512\s*\(",
            r"CryptoJS\.SHA512",
            r"createHash\s*\(\s*['\"]sha512['\"]",
            r"Crypto\.createHash\s*\(\s*['\"]sha512['\"]",
        ],
    ),
    "sha3": CryptoPattern(
        name="SHA-3",
        aliases=["sha3", "SHA3", "Keccak"],
        patterns=[
            r"\bsha3\s*\(",
            r"\.sha3\s*\(",
            r"CryptoJS\.SHA3",
            r"createHash\s*\(\s*['\"]sha3['\"]",
            r"keccak",
            r"js-sha3",
        ],
    ),
    "blake2": CryptoPattern(
        name="BLAKE2",
        aliases=["blake2", "BLAKE2b", "BLAKE2s"],
        patterns=[
            r"\bblake2",
            r"\.blake2",
            r"CryptoJS\.BLAKE2",
            r"spark-md5",
        ],
    ),
}


HMAC_PATTERNS = {
    "hmac_md5": CryptoPattern(
        name="HMAC-MD5",
        aliases=["hmac-md5", "HMAC-MD5"],
        patterns=[
            r"createHmac\s*\(\s*['\"]md5['\"]",
            r"\.hmac\s*\(\s*['\"]md5['\"]",
            r"CryptoJS\.HmacMD5",
        ],
        requires_key=True,
    ),
    "hmac_sha1": CryptoPattern(
        name="HMAC-SHA1",
        aliases=["hmac-sha1", "HMAC-SHA1"],
        patterns=[
            r"createHmac\s*\(\s*['\"]sha1['\"]",
            r"\.hmac\s*\(\s*['\"]sha1['\"]",
            r"CryptoJS\.HmacSHA1",
        ],
        requires_key=True,
    ),
    "hmac_sha256": CryptoPattern(
        name="HMAC-SHA256",
        aliases=["hmac-sha256", "HMAC-SHA256"],
        patterns=[
            r"createHmac\s*\(\s*['\"]sha256['\"]",
            r"\.hmac\s*\(\s*['\"]sha256['\"]",
            r"CryptoJS\.HmacSHA256",
            r"hmac-sha-256",
        ],
        requires_key=True,
    ),
    "hmac_sha512": CryptoPattern(
        name="HMAC-SHA512",
        aliases=["hmac-sha512", "HMAC-SHA512"],
        patterns=[
            r"createHmac\s*\(\s*['\"]sha512['\"]",
            r"\.hmac\s*\(\s*['\"]sha512['\"]",
            r"CryptoJS\.HmacSHA512",
        ],
        requires_key=True,
    ),
}


AES_PATTERNS = {
    "aes_cbc": CryptoPattern(
        name="AES-CBC",
        aliases=["aes-cbc", "AES-CBC"],
        patterns=[r"AES\.CBC", r"createCipheriv\s*\(\s*['\"]aes-.*-cbc['\"]"],
        mode="CBC",
    ),
    "aes_gcm": CryptoPattern(
        name="AES-GCM",
        aliases=["aes-gcm", "AES-GCM"],
        patterns=[r"AES\.GCM", r"createCipheriv\s*\(\s*['\"]aes-.*-gcm['\"]"],
        mode="GCM",
    ),
}


RSA_PATTERNS = {
    "rsa_pkcs1": CryptoPattern(
        name="RSA-PKCS1",
        aliases=["rsa-pkcs1", "RSA-PKCS1"],
        patterns=[r"RSA\.encrypt.*pkcs1", r"rsa\.encrypt"],
    ),
    "rsa_oaep": CryptoPattern(
        name="RSA-OAEP",
        aliases=["rsa-oaep", "RSA-OAEP"],
        patterns=[r"RSA\.encrypt.*oaep"],
    ),
}


ENCODING_PATTERNS = {
    "base64": CryptoPattern(
        name="Base64",
        aliases=["base64", "Base64", "btoa", "atob"],
        patterns=[r"\bbtoa\s*\(", r"\batob\s*\(", r"CryptoJS\.enc\.Base64"],
        encoding="base64",
    ),
    "hex": CryptoPattern(
        name="Hex",
        aliases=["hex", "Hex"],
        patterns=[r"\.toHex\s*\(", r"\.toString\s*\(\s*16\s*\)", r"CryptoJS\.enc\.Hex"],
        encoding="hex",
    ),
}


CUSTOM_SIGNATURES = {
    "sign": CryptoPattern(
        name="Custom Sign Function",
        aliases=["sign", "signature", "signData"],
        patterns=[r"function\s+sign\s*\(", r"\bsign\s*=\s*function"],
    ),
    "encrypt": CryptoPattern(
        name="Custom Encrypt Function",
        aliases=["encrypt", "encryptData"],
        patterns=[r"function\s+encrypt\s*\(", r"\.encrypt\s*=\s*function"],
    ),
}


SIGNATURE_CONSTRUCTION = {
    "header": {
        "X-Signature": [r"['\"]X-?Signature['\"]"],
        "X-Token": [r"['\"]X-?Token['\"]"],
    },
    "query": {
        "sign": [r"sign\s*=", r"signature\s*="],
    },
}


CRYPTO_LIBRARIES = {
    "crypto-js": ["CryptoJS", "CryptoJS.AES", "CryptoJS.MD5"],
    "nodeCrypto": ["require('crypto')"],
    "webCrypto": ["window.crypto.subtle", "crypto.subtle"],
}


# =============================================================================
# HELPER FUNCTIONS (from original module)
# =============================================================================

def get_all_patterns() -> dict:
    """Get all crypto patterns combined"""
    all_patterns = {}
    all_patterns.update(HASH_PATTERNS)
    all_patterns.update(HMAC_PATTERNS)
    all_patterns.update(AES_PATTERNS)
    all_patterns.update(RSA_PATTERNS)
    all_patterns.update(ENCODING_PATTERNS)
    all_patterns.update(CUSTOM_SIGNATURES)
    return all_patterns


def detect_crypto_usage(source_code: str) -> list:
    """Detect crypto usage in source code"""
    results = []
    for name, pattern in get_all_patterns().items():
        matches = 0
        for pattern_str in pattern.patterns:
            if re.search(pattern_str, source_code, re.IGNORECASE):
                matches += 1
        if matches > 0:
            confidence = min(0.3 + matches * 0.2, 0.95)
            results.append((name, confidence))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def get_signature_location(source_code: str) -> dict:
    """Detect where signatures are placed in the code"""
    locations = {"header": [], "query": [], "body": []}
    for location_type, patterns in SIGNATURE_CONSTRUCTION.items():
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                if re.search(pattern, source_code, re.IGNORECASE):
                    locations[location_type].append(field)
                    break
    return locations


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Re-exported from new location
    "CryptoPattern",
    "CryptoPatterns",
    "CryptoType",
    "CryptoAlgorithm",
    "CryptoOperation",
    "CryptoAnalysis",
    "UniversalCryptoDetector",
    # Original patterns (for backward compatibility)
    "HASH_PATTERNS",
    "HMAC_PATTERNS",
    "AES_PATTERNS",
    "RSA_PATTERNS",
    "ENCODING_PATTERNS",
    "CUSTOM_SIGNATURES",
    "SIGNATURE_CONSTRUCTION",
    "CRYPTO_LIBRARIES",
    # Original helper functions
    "get_all_patterns",
    "detect_crypto_usage",
    "get_signature_location",
]
