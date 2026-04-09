"""Cap-2: Pluggable proxy layer for IP reputation defense.

Supports direct (no proxy), static, and rotating proxy modes.
Integrates with RiskControlService: when a 403/429 is detected, the
ProxyManager can rotate to the next available proxy automatically.

Usage::

    pm = ProxyManager(ProxyConfig(mode="rotating", url="http://user:pass@host:port"))
    proxy_url = pm.get_proxy("example.com")       # "http://..." or None
    pm.mark_blocked(proxy_url, "example.com")     # signal this proxy is blocked
    pm.rotate()                                      # pick next proxy
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class ProxyConfig:
    """Configuration for the proxy layer."""
    mode: str = "direct"                     # "direct" | "static" | "rotating"
    url: str = ""                            # "http://user:pass@host:port" (single proxy)
    urls: list[str] = field(default_factory=list)  # multiple proxies for rotating mode
    rotation_after_n_requests: int = 10
    provider: str = ""                       # "brightdata" | "oxylabs" | ""
    provider_api_key: str = ""
    # Auto-rotate on these HTTP status codes
    rotate_on_status: list[int] = field(default_factory=lambda: [403, 429, 503])


@dataclass
class _ProxyRecord:
    url: str
    request_count: int = 0
    blocked_domains: set[str] = field(default_factory=set)
    last_blocked_at: dict[str, float] = field(default_factory=dict)
    success_count: int = 0
    fail_count: int = 0

    @property
    def health_score(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total


class ProxyManager:
    """Selects and rotates proxies for outbound requests.

    When ``mode="direct"``, all methods are no-ops and ``get_proxy()`` returns None.
    When ``mode="static"``, always returns the configured proxy URL.
    When ``mode="rotating"``, rotates after ``rotation_after_n_requests`` or on block signal.

    Integration points:
    - ``driver.py``: pass ``proxy={"server": pm.get_proxy(domain)}`` to Playwright launch
    - ``base_crawler_template.py``: pass ``proxies={"https": pm.get_proxy(domain)}`` to curl_cffi
    - ``s1_crawl.py``: call ``pm.mark_blocked(...)`` when risk_signal fires, then ``pm.rotate()``
    """

    def __init__(self, config: ProxyConfig | None = None) -> None:
        self._config = config or ProxyConfig(mode="direct")
        self._records: list[_ProxyRecord] = []
        self._current_index: int = 0
        self._domain_request_counts: dict[str, int] = {}
        self._total_requests: int = 0

        if self._config.mode != "direct":
            urls = self._config.urls or ([self._config.url] if self._config.url else [])
            self._records = [_ProxyRecord(url=url) for url in urls if url]
            if not self._records:
                log.warning("proxy_manager_no_urls_configured", mode=self._config.mode)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get_proxy(self, domain: str = "") -> str | None:
        """Return the current proxy URL, or None for direct connection."""
        if self._config.mode == "direct" or not self._records:
            return None

        self._total_requests += 1
        if domain:
            self._domain_request_counts[domain] = self._domain_request_counts.get(domain, 0) + 1

        # Auto-rotate after N requests
        if self._config.rotation_after_n_requests > 0:
            if self._total_requests % self._config.rotation_after_n_requests == 0:
                self._advance()

        record = self._current_record()
        if record is None:
            return None
        record.request_count += 1
        return record.url

    def mark_blocked(self, proxy_url: str, domain: str) -> None:
        """Signal that *proxy_url* has been blocked for *domain*.

        The manager will rotate to the next available proxy.
        """
        for record in self._records:
            if record.url == proxy_url:
                record.blocked_domains.add(domain)
                record.last_blocked_at[domain] = time.time()
                record.fail_count += 1
                log.info("proxy_blocked", proxy=proxy_url[:30], domain=domain)
                break
        self.rotate()

    def mark_success(self, proxy_url: str) -> None:
        for record in self._records:
            if record.url == proxy_url:
                record.success_count += 1
                break

    def rotate(self) -> None:
        """Advance to the next proxy in the pool."""
        if len(self._records) > 1:
            self._advance()

    def reset_counts(self) -> None:
        """Reset all request counters (useful between pipeline runs)."""
        self._total_requests = 0
        self._domain_request_counts.clear()

    # ------------------------------------------------------------------
    # Playwright / curl_cffi integration helpers
    # ------------------------------------------------------------------

    def playwright_proxy(self, domain: str = "") -> dict[str, str] | None:
        """Return a Playwright ``proxy`` kwarg dict, or None for direct."""
        url = self.get_proxy(domain)
        if not url:
            return None
        return {"server": url}

    def curl_cffi_proxies(self, domain: str = "") -> dict[str, str] | None:
        """Return a curl_cffi ``proxies`` dict, or None for direct."""
        url = self.get_proxy(domain)
        if not url:
            return None
        return {"http": url, "https": url}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_record(self) -> _ProxyRecord | None:
        if not self._records:
            return None
        return self._records[self._current_index % len(self._records)]

    def _advance(self) -> None:
        if not self._records:
            return
        # Skip proxies with very low health
        start = self._current_index
        for _ in range(len(self._records)):
            self._current_index = (self._current_index + 1) % len(self._records)
            rec = self._records[self._current_index]
            if rec.health_score >= 0.3:
                return
        # All proxies are unhealthy — still advance to avoid infinite loop
        self._current_index = (start + 1) % len(self._records)

    @property
    def mode(self) -> str:
        return self._config.mode

    @property
    def current_url(self) -> str | None:
        rec = self._current_record()
        return rec.url if rec else None

    @property
    def pool_size(self) -> int:
        return len(self._records)
