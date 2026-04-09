from __future__ import annotations

from urllib.parse import urlsplit


_MULTI_LABEL_SUFFIXES = {
    "co.id",
    "co.jp",
    "co.kr",
    "co.th",
    "co.uk",
    "com.ar",
    "com.au",
    "com.bd",
    "com.br",
    "com.cn",
    "com.hk",
    "com.mm",
    "com.mx",
    "com.my",
    "com.np",
    "com.ph",
    "com.pk",
    "com.sg",
    "com.tr",
    "com.tw",
    "com.vn",
    "net.cn",
    "org.cn",
}


def extract_site_domain(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if not raw:
        return ""

    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or raw).strip(".").lower()
    if not host:
        return ""
    if host == "localhost" or host.replace(".", "").isdigit():
        return host

    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return ".".join(parts)

    suffix = ".".join(parts[-2:])
    if suffix in _MULTI_LABEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def extract_domain(url_or_host: str) -> str:
    """Alias for extract_site_domain"""
    return extract_site_domain(url_or_host)


def normalize_url(url: str) -> str:
    """Normalize URL to standard format"""
    if not url:
        return ""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url
