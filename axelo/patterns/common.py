"""
主流网站常见逆向模式库。
这里记录的是公开已知的、已被广泛研究的 JS 签名模式类型，
用于指导 AI 分析方向，不包含任何实际密钥或实现。
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SiteProfile:
    """某类站点的典型逆向特征"""
    category: str                        # 站点分类
    domain_patterns: list[str]           # 域名特征（用于模糊匹配）
    typical_algorithm: str               # 典型签名算法
    difficulty: str                      # easy/medium/hard/extreme
    token_fields: list[str]              # 典型的 token 请求头
    key_signals: list[str]               # 在 JS 中的关键特征字符串
    analysis_hints: list[str]            # 给 AI 的分析提示
    strategy: str                        # python_reconstruct / js_bridge


# 主流站点模式库
KNOWN_PROFILES: list[SiteProfile] = [

    # ── 电商 ────────────────────────────────────────────────────
    SiteProfile(
        category="e-commerce-cn",
        domain_patterns=["jd.com", "taobao.com", "tmall.com", "pinduoduo.com"],
        typical_algorithm="hmac-sha256 with timestamp+nonce",
        difficulty="hard",
        token_fields=["x-sign", "x-api-eid-token", "x-referer-page"],
        key_signals=["sign", "timestamp", "algo", "cipher"],
        analysis_hints=[
            "通常使用设备指纹 + HMAC-SHA256",
            "密钥可能动态从接口获取，注意 /api/xxx/getSecret 类接口",
            "部分平台使用 React Native bridge 需要特殊处理",
        ],
        strategy="js_bridge",
    ),

    SiteProfile(
        category="e-commerce-global",
        domain_patterns=["amazon.com", "ebay.com", "shopify.com"],
        typical_algorithm="custom-hmac or device-fingerprint",
        difficulty="hard",
        token_fields=["x-amzn-requestid", "anti-csrftoken-a2z"],
        key_signals=["ubid", "session-id", "deviceFingerprint"],
        analysis_hints=[
            "Amazon 使用多层签名，重点关注 ue_id 和 session-id 生成",
            "注意 canvas fingerprint 在设备标识中的作用",
        ],
        strategy="js_bridge",
    ),

    # ── 内容/视频平台 ───────────────────────────────────────────
    SiteProfile(
        category="video-cn",
        domain_patterns=["bilibili.com", "iqiyi.com", "youku.com", "douyin.com", "kuaishou.com"],
        typical_algorithm="md5 or hmac with wbi/buvid",
        difficulty="hard",
        token_fields=["w_rid", "wts", "x-argus", "x-bili-aurora-eid"],
        key_signals=["wbi", "buvid", "uuid", "w_rid", "mixin_key"],
        analysis_hints=[
            "B站 WBI 签名：img_key + sub_key 混合后取特定位置字符作为 key",
            "抖音 X-Argus/X-Ladon 基于设备指纹 + 请求体 HMAC",
            "通常需要先获取 nav 接口的 wbi_img 作为 key 材料",
        ],
        strategy="python_reconstruct",
    ),

    # ── 搜索/内容 ────────────────────────────────────────────────
    SiteProfile(
        category="search-cn",
        domain_patterns=["baidu.com", "sogou.com"],
        typical_algorithm="md5-params-salt",
        difficulty="medium",
        token_fields=["sign", "wd", "pn"],
        key_signals=["sign", "cid", "from", "pu"],
        analysis_hints=[
            "百度通常是 MD5(params sorted + salt)",
            "salt 可能在 JS 中硬编码或通过接口获取",
        ],
        strategy="python_reconstruct",
    ),

    # ── 社交媒体 ────────────────────────────────────────────────
    SiteProfile(
        category="social-cn",
        domain_patterns=["weibo.com", "zhihu.com", "xiaohongshu.com"],
        typical_algorithm="rsa or hmac",
        difficulty="hard",
        token_fields=["x-s", "x-t", "authorization"],
        key_signals=["_encode", "sign", "xs", "xt", "x-s"],
        analysis_hints=[
            "小红书 x-s 参数使用 AES+RSA 组合加密",
            "知乎 authorization 基于 timestamp + device_id",
        ],
        strategy="js_bridge",
    ),

    # ── 金融/支付 ────────────────────────────────────────────────
    SiteProfile(
        category="fintech",
        domain_patterns=["alipay.com", "paypal.com", "stripe.com"],
        typical_algorithm="rsa-2048 or custom",
        difficulty="extreme",
        token_fields=["x-sign", "x-tsp", "x-traceid"],
        key_signals=["rsa", "rsaSign", "pubKey", "encrypt"],
        analysis_hints=[
            "支付平台通常使用 RSA，公钥嵌在 JS 中",
            "高度混淆，需要 isolated-vm 沙箱执行",
            "可能有服务器端随机 challenge，需要多次请求",
        ],
        strategy="js_bridge",
    ),

    # ── 旅行/酒店 ────────────────────────────────────────────────
    SiteProfile(
        category="travel-cn",
        domain_patterns=["ctrip.com", "meituan.com", "dianping.com"],
        typical_algorithm="hmac-sha256 or custom-obfuscated",
        difficulty="hard",
        token_fields=["x-trip-payload", "_token", "cticket"],
        key_signals=["tripPayload", "cticket", "mtgsig", "falcon"],
        analysis_hints=[
            "携程 _token 使用设备绑定的 HMAC",
            "美团 mtgsig 基于时序分析 + 环境指纹",
        ],
        strategy="js_bridge",
    ),

    # ── 通用 SPA ────────────────────────────────────────────────
    SiteProfile(
        category="generic-spa",
        domain_patterns=[],  # 兜底匹配
        typical_algorithm="hmac-sha256-timestamp",
        difficulty="medium",
        token_fields=["x-sign", "authorization", "x-token"],
        key_signals=["sign", "timestamp", "nonce", "hmac"],
        analysis_hints=[
            "先检查 HMAC-SHA256(timestamp + nonce + sorted_params, secretKey) 模式",
            "注意 webpack chunk 中可能有内联的 secret key",
        ],
        strategy="python_reconstruct",
    ),
]


def match_profile(url: str) -> SiteProfile | None:
    """根据 URL 匹配最合适的站点模式"""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    for profile in KNOWN_PROFILES:
        for pat in profile.domain_patterns:
            if pat and pat in host:
                return profile
    # 返回通用兜底
    return None
