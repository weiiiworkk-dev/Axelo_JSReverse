"""
Standard Traffic Data Format

Defines the universal data format for representing website traffic
in a standardized way that can be processed by the reverse engine.

This is the foundation of the Universal Reverse Engine.

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class RequestMethod(str, Enum):
    """HTTP Request Methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParameterLocation(str, Enum):
    """Where a parameter can be located"""
    URL_QUERY = "url_query"
    URL_PATH = "url_path"
    HEADER = "header"
    COOKIE = "cookie"
    BODY_FORM = "body_form"
    BODY_JSON = "body_json"
    BODY_RAW = "body_raw"


class SignatureType(str, Enum):
    """Types of signatures"""
    HMAC_MD5 = "hmac_md5"
    HMAC_SHA1 = "hmac_sha1"
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"
    AES_CBC = "aes_cbc"
    AES_GCM = "aes_gcm"
    AES_CTR = "aes_ctr"
    RSA_PKCS1 = "rsa_pkcs1"
    RSA_OAEP = "rsa_oaep"
    CUSTOM_HASH = "custom_hash"
    CUSTOM_ENCRYPT = "custom_encrypt"
    UNKNOWN = "unknown"


class KeySource(str, Enum):
    """Where the signature key comes from"""
    STATIC_CODE = "static_code"      # Hardcoded in JS
    STATIC_CONFIG = "static_config"  # In config/API response
    DYNAMIC_COOKIE = "dynamic_cookie"  # From cookie
    DYNAMIC_HEADER = "dynamic_header"  # From server header
    DYNAMIC_RESPONSE = "dynamic_response"  # From API response
    DYNAMIC_COMPUTED = "dynamic_computed"  # Computed from other params
    USER_INPUT = "user_input"        # From user/environment
    UNKNOWN = "unknown"


# =============================================================================
# CORE DATA STRUCTURES
# =============================================================================

@dataclass
class URLInfo:
    """Standardized URL information"""
    raw_url: str
    scheme: str = ""
    host: str = ""
    port: int = 0
    path: str = ""
    query_params: dict[str, str] = field(default_factory=dict)
    fragment: str = ""
    
    @classmethod
    def parse(cls, url: str) -> URLInfo:
        """Parse URL into components"""
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(url)
        
        query_params = {}
        if parsed.query:
            # Keep first value for each param
            for k, v in parse_qs(parsed.query).items():
                query_params[k] = v[0] if v else ""
        
        return cls(
            raw_url=url,
            scheme=parsed.scheme,
            host=parsed.hostname or "",
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            path=parsed.path,
            query_params=query_params,
            fragment=parsed.fragment,
        )


@dataclass
class HTTPHeaders:
    """Standardized HTTP headers"""
    raw: dict[str, str] = field(default_factory=dict)
    
    def get(self, key: str, default: str = "") -> str:
        """Get header case-insensitively"""
        key_lower = key.lower()
        for k, v in self.raw.items():
            if k.lower() == key_lower:
                return v
        return default
    
    def has(self, key: str) -> bool:
        """Check if header exists"""
        return self.get(key) != ""
    
    def to_dict(self) -> dict[str, str]:
        """Convert to dict"""
        return dict(self.raw)


@dataclass
class RequestInfo:
    """Standardized request information"""
    method: RequestMethod = RequestMethod.GET
    url: URLInfo = field(default_factory=URLInfo)
    headers: HTTPHeaders = field(default_factory=HTTPHeaders)
    body: Optional[str] = None
    body_type: str = "none"  # none, json, form, text, binary
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_raw(cls, method: str, url: str, headers: dict = None, body: Any = None) -> RequestInfo:
        """Create from raw request data"""
        url_info = URLInfo.parse(url)
        
        http_headers = HTTPHeaders(raw=headers or {})
        
        # Determine body type
        body_type = "none"
        body_str = None
        if body:
            if isinstance(body, dict):
                body_type = "json"
                import json
                body_str = json.dumps(body)
            elif isinstance(body, str):
                body_type = "text"
                body_str = body
        
        return cls(
            method=RequestMethod(method.upper()),
            url=url_info,
            headers=http_headers,
            body=body_str,
            body_type=body_type,
        )


@dataclass
class ResponseInfo:
    """Standardized response information"""
    status_code: int = 0
    status_text: str = ""
    headers: HTTPHeaders = field(default_factory=HTTPHeaders)
    body: Optional[str] = None
    body_type: str = "none"  # none, json, text, html, binary
    content_length: int = 0
    timestamp: float = field(default_factory=time.time)
    response_time: float = 0.0  # milliseconds


@dataclass
class TrafficPair:
    """A request-response pair"""
    request: RequestInfo
    response: ResponseInfo
    
    # Derived information
    is_api_call: bool = False
    contains_signature: bool = False
    signature_param_names: list[str] = field(default_factory=list)


@dataclass
class JavaScriptBundle:
    """JavaScript code bundle information"""
    url: str
    content: str
    size: int = 0
    is_obfuscated: bool = False
    obfuscation_type: str = "none"  # none, minified, packed, custom
    detected_algorithms: list[str] = field(default_factory=list)
    string_literals: list[str] = field(default_factory=list)
    function_signatures: list[dict] = field(default_factory=list)


# =============================================================================
# SIGNATURE INFORMATION
# =============================================================================

@dataclass
class SignatureInput:
    """A single input to the signature algorithm"""
    name: str
    location: ParameterLocation
    value: Any
    is_generated: bool = False  # True if generated (timestamp, nonce)
    generation_method: Optional[str] = None


@dataclass
class SignatureKey:
    """Information about the signature key"""
    source: KeySource
    value: Optional[str] = None
    location: Optional[str] = None  # Where to find it
    extraction_method: Optional[str] = None


@dataclass
class SignatureAlgorithm:
    """Information about the signature algorithm"""
    type: SignatureType
    confidence: float = 0.0
    variant: Optional[str] = None  # e.g., "hmac-sha256"
    
    @classmethod
    def unknown(cls, confidence: float = 0.0) -> SignatureAlgorithm:
        return cls(type=SignatureType.UNKNOWN, confidence=confidence)


@dataclass
class SignatureOutput:
    """Where the signature is placed"""
    location: ParameterLocation
    name: str  # Parameter/header name
    format: str = "raw"  # raw, base64, hex, url


@dataclass
class SignatureHypothesis:
    """Complete signature hypothesis"""
    algorithm: SignatureAlgorithm
    inputs: list[SignatureInput] = field(default_factory=list)
    key: SignatureKey = field(default_factory=lambda: SignatureKey(source=KeySource.UNKNOWN))
    output: SignatureOutput = field(default_factory=lambda: SignatureOutput(
        location=ParameterLocation.HEADER, name="X-Sign"
    ))
    construction_steps: list[str] = field(default_factory=list)  # Ordered steps
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm.type.value,
            "inputs": [(i.name, i.location.value) for i in self.inputs],
            "key_source": self.key.source.value,
            "output": (self.output.location.value, self.output.name),
            "confidence": self.confidence,
        }


# =============================================================================
# COMPLETE TRAFFIC CONTEXT
# =============================================================================

@dataclass
class StandardTraffic:
    """
    Complete standardized traffic context
    
    This is the main data structure that all other modules work with.
    """
    # Traffic pairs
    traffic_pairs: list[TrafficPair] = field(default_factory=list)
    
    # JavaScript bundles
    js_bundles: list[JavaScriptBundle] = field(default_factory=list)
    
    # Website metadata
    url: str = ""
    domain: str = ""
    is_login_required: bool = False
    
    # Timing information
    first_request_time: float = 0.0
    last_request_time: float = 0.0
    
    # Additional context
    user_agent: str = ""
    session_id: Optional[str] = None
    
    # Analysis results
    signature_hypothesis: Optional[SignatureHypothesis] = None
    complexity_score: float = 0.0  # 0-1, how complex the signature is
    
    # Metadata
    collected_at: float = field(default_factory=time.time)
    collection_method: str = "unknown"  # browser, proxy, har
    
    def get_first_request(self) -> Optional[RequestInfo]:
        """Get first request"""
        return self.traffic_pairs[0].request if self.traffic_pairs else None
    
    def get_last_request(self) -> Optional[RequestInfo]:
        """Get last request"""
        return self.traffic_pairs[-1].request if self.traffic_pairs else None
    
    def get_all_urls(self) -> list[str]:
        """Get all URLs from traffic"""
        return [pair.request.url.raw_url for pair in self.traffic_pairs]
    
    def get_api_calls(self) -> list[TrafficPair]:
        """Get only API calls"""
        return [pair for pair in self.traffic_pairs if pair.is_api_call]
    
    def has_signature(self) -> bool:
        """Check if any signature detected"""
        return any(pair.contains_signature for pair in self.traffic_pairs)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_from_browser_traffic(
    requests: list[dict],
    responses: list[dict],
    js_code: list[str] = None,
) -> StandardTraffic:
    """
    Create StandardTraffic from browser traffic capture
    
    Args:
        requests: List of captured requests (dict format)
        responses: List of captured responses
        js_code: Optional JavaScript code
        
    Returns:
        StandardTraffic instance
    """
    traffic = StandardTraffic()
    traffic.collection_method = "browser"
    
    for req, resp in zip(requests, responses):
        # Parse request
        request = RequestInfo.from_raw(
            method=req.get("method", "GET"),
            url=req.get("url", ""),
            headers=req.get("headers", {}),
            body=req.get("postData", {}),
        )
        
        # Parse response
        response = ResponseInfo(
            status_code=resp.get("status", 0),
            status_text=resp.get("statusText", ""),
            body=resp.get("content", {}).get("text", ""),
        )
        
        pair = TrafficPair(request=request, response=response)
        
        # Detect if it's an API call
        if "/api/" in request.url.path or ".json" in request.url.path:
            pair.is_api_call = True
        
        # Detect signature parameters
        for key in request.url.query_params:
            if any(s in key.lower() for s in ["sign", "token", "key", "auth"]):
                pair.contains_signature = True
                pair.signature_param_names.append(key)
        
        traffic.traffic_pairs.append(pair)
    
    # Add JS bundles
    if js_code:
        for i, code in enumerate(js_code):
            traffic.js_bundles.append(JavaScriptBundle(
                url=f"inline_script_{i}",
                content=code,
                size=len(code),
            ))
    
    # Set domain
    if traffic.traffic_pairs:
        traffic.url = traffic.traffic_pairs[0].request.url.raw_url
        traffic.domain = traffic.traffic_pairs[0].request.url.host
    
    return traffic


def create_from_har(har_data: dict) -> StandardTraffic:
    """Create StandardTraffic from HAR file"""
    traffic = StandardTraffic()
    traffic.collection_method = "har"
    
    for entry in har_data.get("log", {}).get("entries", []):
        request_data = entry.get("request", {})
        response_data = entry.get("response", {})
        
        # Extract request
        headers = {}
        for h in request_data.get("headers", []):
            headers[h["name"]] = h["value"]
        
        request = RequestInfo.from_raw(
            method=request_data.get("method", "GET"),
            url=request_data.get("url", ""),
            headers=headers,
            body=request_data.get("postData", {}).get("text") if request_data.get("postData") else None,
        )
        
        # Extract response
        response = ResponseInfo(
            status_code=response_data.get("status", 0),
            body=response_data.get("content", {}).get("text"),
        )
        
        pair = TrafficPair(request=request, response=response)
        traffic.traffic_pairs.append(pair)
    
    return traffic


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "RequestMethod",
    "ParameterLocation",
    "SignatureType",
    "KeySource",
    # Core structures
    "URLInfo",
    "HTTPHeaders",
    "RequestInfo",
    "ResponseInfo",
    "TrafficPair",
    "JavaScriptBundle",
    # Signature
    "SignatureInput",
    "SignatureKey",
    "SignatureAlgorithm",
    "SignatureOutput",
    "SignatureHypothesis",
    # Main
    "StandardTraffic",
    # Utilities
    "create_from_browser_traffic",
    "create_from_har",
]