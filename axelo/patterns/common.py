"""
通用逆向模式库（站点无关）。
仅按技术特征分类，不包含任何站点域名或品牌映射。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SiteProfile:
    """站点无关的逆向特征档案"""
    category: str
    typical_algorithm: str
    difficulty: str  # easy/medium/hard/extreme
    token_fields: list[str]
    key_signals: list[str]
    analysis_hints: list[str]
    strategy: str  # python_reconstruct / js_bridge


KNOWN_PROFILES: list[SiteProfile] = [
    SiteProfile(
        category="generic-spa",
        typical_algorithm="hmac-sha256 with timestamp+nonce",
        difficulty="medium",
        token_fields=["x-sign", "authorization", "x-token"],
        key_signals=["sign", "timestamp", "nonce", "hmac"],
        analysis_hints=[
            "优先检查参数排序 + 时间戳 + 随机数的签名链路",
            "留意 webpack chunk 中的内联 key 材料",
        ],
        strategy="python_reconstruct",
    ),
    SiteProfile(
        category="api-gateway-protected",
        typical_algorithm="rsa or aes-hmac hybrid",
        difficulty="hard",
        token_fields=["x-sign", "x-traceid", "x-request-id"],
        key_signals=["encrypt", "rsa", "aes", "signature", "token"],
        analysis_hints=[
            "关注网关前置鉴权字段与签名拼接顺序",
            "若 key 动态下发，先定位初始化接口和缓存位置",
        ],
        strategy="js_bridge",
    ),
]


def match_profile(url: str) -> SiteProfile | None:
    """返回通用默认档案，避免站点级微调。"""
    _ = url
    return KNOWN_PROFILES[0] if KNOWN_PROFILES else None
