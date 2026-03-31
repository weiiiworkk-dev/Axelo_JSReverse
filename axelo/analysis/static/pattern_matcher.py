from __future__ import annotations
import re
from axelo.models.analysis import TokenCandidate, TokenType, FunctionSignature

# 加密特征关键词
CRYPTO_SIGNATURES: list[tuple[TokenType, list[str]]] = [
    ("hmac",      ["hmac", "HMAC", "createHmac", "HmacSHA"]),
    ("sha256",    ["sha256", "SHA256", "sha-256", "digest"]),
    ("md5",       ["md5", "MD5", "createHash"]),
    ("aes",       ["aes", "AES", "encrypt", "decrypt", "cipher"]),
    ("base64",    ["btoa", "atob", "base64", "toBase64", "fromBase64"]),
    ("timestamp", ["Date.now", "getTime", "timestamp", "ts", "_t", "nonce"]),
    ("fingerprint", ["fingerprint", "canvas", "webgl", "deviceId", "device_id"]),
]

# 请求头/字段特征（用于推断 request_field）
HEADER_PATTERNS: list[tuple[str, list[str]]] = [
    ("X-Sign",       ["sign", "signature", "_sign", "x_sign"]),
    ("X-Token",      ["token", "accessToken", "access_token"]),
    ("X-Nonce",      ["nonce", "_nonce", "nonceStr"]),
    ("X-Timestamp",  ["timestamp", "_t", "ts"]),
    ("Authorization", ["auth", "bearer", "jwt", "Authorization"]),
]


def score_function(
    func: FunctionSignature,
    ast_metadata: dict,
) -> list[TokenCandidate]:
    """
    对单个函数打分，返回零个或多个 TokenCandidate。
    """
    candidates: list[TokenCandidate] = []
    source = func.raw_source.lower()
    name = (func.name or "").lower()

    # 检查是否调用了加密API
    for token_type, keywords in CRYPTO_SIGNATURES:
        evidence: list[str] = []
        for kw in keywords:
            if kw.lower() in source or kw.lower() in name:
                evidence.append(f"包含关键词 '{kw}'")
        if not evidence:
            continue

        # 基础置信度
        confidence = min(0.3 + len(evidence) * 0.15, 0.85)

        # 函数名加分（函数名本身就有意义）
        if any(kw.lower() in name for kw in keywords):
            confidence = min(confidence + 0.1, 0.95)

        # 推断对应的请求字段
        request_field = _infer_request_field(name, source)

        candidates.append(TokenCandidate(
            func_id=func.func_id,
            token_type=token_type,
            confidence=confidence,
            evidence=evidence,
            request_field=request_field,
            source_snippet=func.raw_source[:500],
        ))

    return candidates


def _infer_request_field(name: str, source: str) -> str | None:
    combined = name + " " + source
    for field, patterns in HEADER_PATTERNS:
        for pat in patterns:
            if pat.lower() in combined:
                return field
    return None


def scan_string_constants(string_literals: list[str]) -> list[str]:
    """
    从字符串常量中筛选出可能是密钥/算法标识的字符串。
    """
    interesting: list[str] = []
    key_patterns = [
        re.compile(r'^[A-Za-z0-9+/]{8,}={0,2}$'),   # base64-like (≥6 bytes)
        re.compile(r'^[0-9a-fA-F]{16,}$'),             # hex key
        re.compile(r'hmac|sha|aes|md5|sign|token', re.I),
    ]
    for s in string_literals:
        if any(p.search(s) for p in key_patterns):
            interesting.append(s)
    return interesting[:50]
