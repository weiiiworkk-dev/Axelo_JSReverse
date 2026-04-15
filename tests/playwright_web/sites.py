"""8 个目标网站的测试配置。

重要设计原则：
- 所有 goal 均为通用性描述，不含任何特定站点的 API 路径、参数名等细节。
- 系统通过自身的通用逆向能力来完成任务，而非依赖特化逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SiteConfig:
    name: str        # 用于目录命名，全小写
    url: str         # 目标 URL（搜索结果页，能触发 API 调用）
    goal: str        # 通用任务目标描述
    stealth: str = "high"
    js_rendering: str = "auto"
    verify: bool = True


SITES: list[SiteConfig] = [
    SiteConfig(
        name="amazon",
        url="https://www.amazon.com/s?k=laptop",
        goal=(
            "Reverse engineer the product search API and any request signing mechanism. "
            "Identify how signed parameters or tokens are generated and attached to requests. "
            "Extract the crawl schema for product listings including price, title, ASIN, and rating."
        ),
    ),
    SiteConfig(
        name="lazada",
        url="https://www.lazada.com/catalog/?q=laptop",
        goal=(
            "Reverse engineer the product search API transport. "
            "Identify request signing, token generation, or anti-bot challenge mechanisms. "
            "Extract crawl schema for product listings including price, title, and seller."
        ),
    ),
    SiteConfig(
        name="ebay",
        url="https://www.ebay.com/sch/i.html?_nkw=laptop",
        goal=(
            "Reverse engineer the product search API and any session or token requirements. "
            "Extract the crawl schema for listings including price, title, item ID, and condition."
        ),
    ),
    SiteConfig(
        name="shopee",
        url="https://shopee.com/search?keyword=laptop",
        goal=(
            "Reverse engineer the product search API and request signing mechanism. "
            "Identify how anti-bot tokens or signatures are computed. "
            "Extract crawl schema for product listings."
        ),
    ),
    SiteConfig(
        name="temu",
        url="https://www.temu.com/search_result.html?search_key=laptop",
        goal=(
            "Reverse engineer the product search API and any signing or fingerprinting mechanism. "
            "Extract crawl schema for product listings including price, title, and goods ID."
        ),
    ),
    SiteConfig(
        name="jd",
        url="https://search.jd.com/Search?keyword=laptop",
        goal=(
            "逆向工程产品搜索 API 和请求签名机制。"
            "识别签名参数、时间戳或反爬 token 的生成逻辑。"
            "提取商品列表爬取 schema，包括价格、标题、商品 ID 和评分。"
        ),
    ),
    SiteConfig(
        name="taobao",
        url="https://s.taobao.com/search?q=laptop",
        goal=(
            "逆向工程商品搜索 API 及请求签名机制（如 sign、_uab_collina 等参数）。"
            "分析前端 JS 中的签名生成逻辑与加密算法。"
            "提取商品列表爬取 schema，包括价格、标题、店铺名和商品 ID。"
        ),
    ),
    SiteConfig(
        name="pinduoduo",
        url="https://www.pinduoduo.com/search_result.html?search_key=laptop",
        goal=(
            "逆向工程商品搜索 API 及请求签名机制（如 anti_content、sign 等参数）。"
            "分析 JS 混淆代码中的签名生成逻辑与反爬机制。"
            "提取商品列表爬取 schema，包括价格、标题、商品 ID 和销量。"
        ),
    ),
]

SITE_MAP: dict[str, SiteConfig] = {s.name: s for s in SITES}
