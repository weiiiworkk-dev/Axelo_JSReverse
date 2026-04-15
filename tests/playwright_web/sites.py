"""
通用测试目标配置 — 仅验证系统逆向与爬虫通用能力。

设计原则：
- 所有目标均选自公开的、专为测试/爬虫设计的站点，
  或具有典型技术特征（签名、反爬、JS 渲染）的公共 API。
- goal 描述均为通用能力目标，不含特定站点专有细节。
- 系统须凭自身通用逆向能力完成任务，不依赖任何预置站点逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SiteConfig:
    name: str
    url: str
    goal: str
    stealth: str = "medium"
    js_rendering: str = "auto"
    verify: bool = True


SITES: list[SiteConfig] = [
    SiteConfig(
        name="quotes_toscrape",
        url="https://quotes.toscrape.com",
        goal=(
            "Extract all quotes from the site. "
            "Reverse engineer the pagination mechanism to crawl all pages. "
            "Schema: quote text, author name, tags. "
            "This is a scraping sandbox — demonstrate generic extraction capability."
        ),
        stealth="low",
        js_rendering="false",
    ),
    SiteConfig(
        name="httpbin_anything",
        url="https://httpbin.org/anything",
        goal=(
            "Analyse the API transport layer and response schema. "
            "Identify all request/response fields and headers. "
            "Demonstrate generic HTTP API reverse engineering capability."
        ),
        stealth="low",
        js_rendering="false",
    ),
    SiteConfig(
        name="books_toscrape",
        url="https://books.toscrape.com",
        goal=(
            "Crawl book listings from the catalogue. "
            "Schema: title, price, availability, star rating, URL. "
            "Reverse engineer the pagination and any session cookies required."
        ),
        stealth="low",
        js_rendering="false",
    ),
    SiteConfig(
        name="quotes_toscrape_js",
        url="https://quotes.toscrape.com/js/",
        goal=(
            "Extract quotes from the JavaScript-rendered version of the site. "
            "Reverse engineer the XHR/fetch calls that load quote data. "
            "Schema: quote text, author, tags. "
            "Demonstrate JS-rendering and dynamic API discovery capability."
        ),
        stealth="low",
        js_rendering="auto",
    ),
]

SITE_MAP: dict[str, SiteConfig] = {s.name: s for s in SITES}
