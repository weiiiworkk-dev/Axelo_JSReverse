from __future__ import annotations
import re
from axelo.models.analysis import TokenCandidate, TokenType, FunctionSignature
from axelo.analysis.static.crypto_patterns import (
    get_all_patterns,
    detect_crypto_usage,
    get_signature_location,
)

# 扩展的加密特征关键词 - 从 crypto_patterns.py 导入
CRYPTO_PATTERNS = get_all_patterns()

# 加密特征关键词 (兼容旧格式)
CRYPTO_SIGNATURES: list[tuple[TokenType, list[str]]] = [
    ("hmac",      ["hmac", "HMAC", "createHmac", "HmacSHA"]),
    ("sha256",    ["sha256", "SHA256", "sha-256", "digest"]),
    ("sha512",    ["sha512", "SHA512", "sha-512"]),
    ("sha1",      ["sha1", "SHA1", "sha-1"]),
    ("md5",       ["md5", "MD5", "createHash"]),
    ("aes",       ["aes", "AES", "encrypt", "decrypt", "cipher"]),
    ("rsa",       ["rsa", "RSA", "encrypt", "sign"]),
    ("base64",    ["btoa", "atob", "base64", "toBase64", "fromBase64"]),
    ("timestamp", ["Date.now", "getTime", "timestamp", "ts", "_t", "nonce"]),
    ("fingerprint", ["fingerprint", "canvas", "webgl", "deviceId", "device_id"]),
    # 新增：更多加密算法
    ("sha3",      ["sha3", "SHA3", "keccak"]),
    ("blake2",    ["blake2", "BLAKE2"]),
    ("ecdsa",     ["ecdsa", "ECDSA", "sign", "verify"]),
]

# 负面模式：UI/DOM/表单函数不应被标记为签名候选
# 匹配时对每个函数的 confidence 减分，避免误报
_DOM_NEGATIVE_PATTERNS = frozenset({
    "document.", "innerhtml", "queryselector", "createelement",
    "textcontent", "classname", "setattribute", "addeventlistener",
    "appendchild", "removechild",
})
_FORM_NEGATIVE_PATTERNS = frozenset({
    "validate", "required field", "form submit", "onsubmit",
    "checkvalidity", "setcustomvalidity",
})
_UI_NEGATIVE_PATTERNS = frozenset({
    "style.", "display:", "animation", "transition",
    "classlist", "dataset.", "scrolltop", "offsetwidth",
})
_NEGATIVE_PENALTY_PER_CATEGORY = 0.2

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
    使用增强的加密模式检测。
    """
    candidates: list[TokenCandidate] = []
    source = func.raw_source.lower()
    name = (func.name or "").lower()

    # 方法1：使用旧的关键词匹配（兼容）
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

    # 方法2：使用新的模式检测（更准确）
    try:
        detected = detect_crypto_usage(func.raw_source)
        for algo, conf in detected:
            # 避免重复添加
            if not any(c.token_type == algo for c in candidates):
                # 转换算法名称到TokenType
                token_type = _algo_to_token_type(algo)
                candidates.append(TokenCandidate(
                    func_id=func.func_id,
                    token_type=token_type,
                    confidence=conf,
                    evidence=[f"模式匹配: {algo}"],
                    request_field=_infer_request_field_from_code(func.raw_source),
                    source_snippet=func.raw_source[:500],
                ))
    except Exception:
        pass  # 如果导入失败，使用旧方法

    # 负面模式降分：UI/DOM/表单函数不应是签名候选
    if candidates:
        penalties = 0
        if any(pat in source for pat in _DOM_NEGATIVE_PATTERNS):
            penalties += 1
        if any(pat in source for pat in _FORM_NEGATIVE_PATTERNS):
            penalties += 1
        if any(pat in source for pat in _UI_NEGATIVE_PATTERNS):
            penalties += 1
        if penalties > 0:
            penalty = penalties * _NEGATIVE_PENALTY_PER_CATEGORY
            candidates = [
                TokenCandidate(
                    func_id=c.func_id,
                    token_type=c.token_type,
                    confidence=max(0.0, round(c.confidence - penalty, 4)),
                    evidence=c.evidence + [f"negative_penalty={penalty:.1f}"],
                    request_field=c.request_field,
                    source_snippet=c.source_snippet,
                )
                for c in candidates
            ]

    return candidates


def _infer_request_field(name: str, source: str) -> str | None:
    combined = name + " " + source
    for field, patterns in HEADER_PATTERNS:
        for pat in patterns:
            if pat.lower() in combined:
                return field
    return None


def _algo_to_token_type(algo: str) -> TokenType:
    """Convert algorithm name to TokenType"""
    mapping = {
        "hmac_md5": "hmac",
        "hmac_sha1": "hmac",
        "hmac_sha256": "hmac",
        "hmac_sha512": "hmac",
        "generic_hmac": "hmac",
        "md5": "md5",
        "sha1": "sha1",
        "sha256": "sha256",
        "sha512": "sha512",
        "sha3": "sha3",
        "blake2": "blake2",
        "aes_cbc": "aes",
        "aes_gcm": "aes",
        "aes_ctr": "aes",
        "aes_ecb": "aes",
        "generic_aes": "aes",
        "rsa_pkcs1": "rsa",
        "rsa_oaep": "rsa",
        "rsa_pss": "rsa",
        "generic_rsa": "rsa",
        "base64": "base64",
        "hex": "hex",
        "utf8": "utf8",
        "url": "url",
        "sign": "sign",
        "encrypt": "encrypt",
        "generate": "token",
        "nonce": "nonce",
        "timestamp": "timestamp",
    }
    return mapping.get(algo, algo)


def _infer_request_field_from_code(source_code: str) -> str | None:
    """Infer signature location from source code"""
    try:
        locations = get_signature_location(source_code)
        # Priority: header > query > body
        if locations.get("header"):
            return locations["header"][0]
        if locations.get("query"):
            return locations["query"][0]
        if locations.get("body"):
            return locations["body"][0]
    except Exception:
        pass
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
