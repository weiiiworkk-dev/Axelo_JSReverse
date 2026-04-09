"""
Known Signature Pattern Library

A database of known signature patterns for common websites and APIs.
This enables faster reverse engineering by recognizing known patterns.

Version: 1.0
Created: 2026-04-06
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignaturePattern:
    """Known signature pattern"""
    id: str
    name: str
    website: str
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
    # =============================================================================
    # Chinese E-commerce
    # =============================================================================
    SignaturePattern(
        id="jd_hmac_sha256",
        name="JD.com HMAC Signature",
        website="jd.com",
        algorithm="hmac-sha256",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["app_key", "timestamp", "method", "format", "v", "sign"],
        header_name="sign",
        notes="Common JD.com API signature method",
        confidence=0.9,
    ),
    SignaturePattern(
        id="taobao_hmac_md5",
        name="Taobao HMAC-MD5 Signature",
        website="taobao.com",
        algorithm="hmac-md5",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["app_secret", "method", "timestamp", "v", "sign"],
        header_name="X-Umeng",
        notes="Taobao open API signature",
        confidence=0.85,
    ),
    SignaturePattern(
        id="alibaba_encrypt",
        name="Alibaba Encrypt",
        website="alibaba.com",
        algorithm="aes",
        key_source="dynamic",
        key_location="Server response",
        parameter_order=["data", "encrypt_key"],
        header_name="X-Ca-Key",
        notes="Alibaba Cloud API Gateway encryption",
        confidence=0.8,
    ),
    
    # =============================================================================
    # Search Engines
    # =============================================================================
    SignaturePattern(
        id="baidu_aes",
        name="Baidu AES Signature",
        website="baidu.com",
        algorithm="aes-cbc",
        key_source="dynamic",
        key_location="Server response",
        parameter_order=["url", "key"],
        header_name="X-Bd-ApiKey",
        notes="Baidu search API encryption",
        confidence=0.9,
    ),
    SignaturePattern(
        id="sogou_encrypt",
        name="Sogou Encrypt",
        website="sogou.com",
        algorithm="custom",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["query", "sign"],
        header_name="Cookie",
        notes="Sogou web search signature",
        confidence=0.75,
    ),
    
    # =============================================================================
    # Video Platforms
    # =============================================================================
    SignaturePattern(
        id="bilibili_hmac_sha256",
        name="Bilibili HMAC-SHA256",
        website="bilibili.com",
        algorithm="hmac-sha256",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["appkey", "sign", "ts"],
        header_name="X-Check-Status",
        notes="Bilibili API signature with appkey",
        confidence=0.95,
    ),
    SignaturePattern(
        id="iqiyi_encrypt",
        name="iQiyi Encrypt",
        website="iqiyi.com",
        algorithm="aes",
        key_source="dynamic",
        key_location="Cookie",
        parameter_order=["param", "sign"],
        header_name="QYP",
        notes="iQiyi video platform signature",
        confidence=0.85,
    ),
    SignaturePattern(
        id="youku_hmac",
        name="Youku HMAC",
        website="youku.com",
        algorithm="hmac-sha1",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["client", "timestamp", "token"],
        header_name="X-Youku-Token",
        notes="Youku video API signature",
        confidence=0.8,
    ),
    
    # =============================================================================
    # Social Media
    # =============================================================================
    SignaturePattern(
        id="weibo_sha1",
        name="Weibo SHA1",
        website="weibo.com",
        algorithm="sha1",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["source", "sign", "time"],
        header_name="Cookie",
        notes="Weibo API signature",
        confidence=0.9,
    ),
    SignaturePattern(
        id="zhihu_encrypt",
        name="Zhihu Encrypt",
        website="zhihu.com",
        algorithm="aes-gcm",
        key_source="dynamic",
        key_location="Server response",
        parameter_order=["headers", "body", "token"],
        header_name="X-Zhihu-Signature",
        notes="Zhihu API encryption",
        confidence=0.85,
    ),
    
    # =============================================================================
    # News & Information
    # =============================================================================
    SignaturePattern(
        id="toutiao_hmac_sha256",
        name="Toutiao HMAC-SHA256",
        website="toutiao.com",
        algorithm="hmac-sha256",
        key_source="static",
        key_location="JS bundle",
        parameter_order=["app_id", "timestamp", "sign"],
        header_name="X-Toutiao-Sign",
        notes="Toutiao (ByteDance) API signature",
        confidence=0.95,
    ),
    SignaturePattern(
        id="zhihu_encrypt",
        name="Wangwang Encrypt",
        website="wangwang.com",
        algorithm="custom",
        key_source="dynamic",
        key_location="Session",
        parameter_order=["user_id", "token"],
        header_name="X-Ww-Token",
        notes="Alibaba Wangwang customer service",
        confidence=0.7,
    ),
    
    # =============================================================================
    # International
    # =============================================================================
    SignaturePattern(
        id="amazon_signature_v4",
        name="AWS Signature V4",
        website="amazonaws.com",
        algorithm="hmac-sha256",
        key_source="static",
        key_location="Configuration",
        parameter_order=["algorithm", "credential", "date", "headers", "payload"],
        header_name="Authorization",
        notes="AWS API request signing (AWS Signature Version 4)",
        confidence=1.0,
    ),
    SignaturePattern(
        id="google_api_key",
        name="Google API Key",
        website="google.com",
        algorithm="none",
        key_source="static",
        key_location="URL parameter",
        parameter_order=["key"],
        header_name="none",
        notes="Google API uses API key in URL, no signature",
        confidence=1.0,
    ),
    SignaturePattern(
        id="facebook_encrypt",
        name="Facebook Encryption",
        website="facebook.com",
        algorithm="aes",
        key_source="dynamic",
        key_location="Cookie",
        parameter_order=["data", "key"],
        header_name="X-Fb-Encryption",
        notes="Facebook Graph API encryption",
        confidence=0.85,
    ),
    SignaturePattern(
        id="twitter_oauth",
        name="Twitter OAuth",
        website="twitter.com",
        algorithm="hmac-sha1",
        key_source="dynamic",
        key_location="OAuth token",
        parameter_order=["oauth_consumer_key", "oauth_token", "timestamp", "nonce"],
        header_name="Authorization",
        notes="Twitter OAuth 1.0a signing",
        confidence=1.0,
    ),
    
    # =============================================================================
    # Common Patterns
    # =============================================================================
    SignaturePattern(
        id="generic_hmac_sha256",
        name="Generic HMAC-SHA256",
        website="*",
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
        website="*",
        algorithm="md5",
        key_source="unknown",
        key_location="unknown",
        parameter_order=["data"],
        header_name="X-Md5",
        notes="Common MD5 pattern - needs manual analysis",
        confidence=0.5,
    ),
]


# =============================================================================
# PATTERN MATCHING
# =============================================================================

class PatternMatcher:
    """Match known patterns against new targets"""
    
    def __init__(self):
        self.patterns = KNOWN_PATTERNS
    
    def match_by_website(self, website: str) -> list[SignaturePattern]:
        """Find patterns matching a website"""
        return [p for p in self.patterns if website in p.website or p.website == "*"]
    
    def match_by_algorithm(self, algorithm: str) -> list[SignaturePattern]:
        """Find patterns by algorithm"""
        return [p for p in self.patterns if algorithm in p.algorithm]
    
    def match_by_key_source(self, key_source: str) -> list[SignaturePattern]:
        """Find patterns by key source"""
        return [p for p in self.patterns if key_source in p.key_source]
    
    def suggest_pattern(self, website: str, algorithm: str = None) -> Optional[SignaturePattern]:
        """Suggest most likely pattern for a website"""
        candidates = self.match_by_website(website)
        
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
