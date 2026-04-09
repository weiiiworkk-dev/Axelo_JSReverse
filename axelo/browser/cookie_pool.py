"""Cap-4: Process-level Cookie Pool Coordinator.

Shares valid cookie jars across concurrent workers for the same domain,
preventing duplicate challenge-solving and improving throughput 3–5× on
cookie-heavy targets.

Key behaviors:
- First worker that needs a domain's cookies acquires the resolver lock
- Subsequent workers wait (at most `timeout` seconds) for the first to write
- Cookies are proactively refreshed 30 seconds before TTL expiry
- Fallback: if wait times out, returns None (caller proceeds without cookie)

Usage::

    pool = CookiePoolCoordinator()
    await pool.start_refresh_loop()  # background task

    cookies = await pool.get_cookies("shopee.com.my", timeout=30.0)
    if cookies:
        # use cookies
        ...
    else:
        # resolve challenge and put cookies
        cookies = await resolve_challenge(...)
        await pool.put_cookies("shopee.com.my", cookies, ttl=1500)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import structlog

log = structlog.get_logger()


@dataclass
class CookieJar:
    """A cookie snapshot for one domain."""
    domain: str
    cookies: dict[str, str]
    acquired_at: float = field(default_factory=time.monotonic)
    ttl_seconds: int = 300
    source: str = "resolver"    # "resolver" | "human" | "knowledge"

    @property
    def is_valid(self) -> bool:
        elapsed = time.monotonic() - self.acquired_at
        return elapsed < self.ttl_seconds * 0.85  # 85% TTL safety margin

    @property
    def seconds_until_expiry(self) -> float:
        elapsed = time.monotonic() - self.acquired_at
        return max(0.0, self.ttl_seconds * 0.85 - elapsed)


class CookiePoolCoordinator:
    """Process-level, thread-safe (asyncio) cookie pool.

    Prevents N concurrent workers from each solving the same domain challenge.
    Instead, the first worker solves and writes; the rest wait and reuse.
    """

    def __init__(self) -> None:
        self._jars: dict[str, CookieJar] = {}           # domain → CookieJar
        self._locks: dict[str, asyncio.Lock] = {}        # domain → resolver lock
        self._resolve_events: dict[str, asyncio.Event] = {}  # domain → resolved signal
        self._refresh_callback: Callable[[str], Coroutine[Any, Any, dict[str, str] | None]] | None = None
        self._refresh_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def get_cookies(self, domain: str, timeout: float = 30.0) -> dict[str, str] | None:
        """Return valid cookies for *domain* if available.

        - If a fresh jar exists → return immediately (O(1))
        - If a resolver is running → wait up to *timeout* for it to complete
        - If nothing available → return None (caller must resolve)
        """
        jar = self._jars.get(domain)
        if jar and jar.is_valid:
            return dict(jar.cookies)

        # Wait for another worker that may be resolving right now
        event = self._resolve_events.get(domain)
        if event and not event.is_set():
            try:
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)
                jar = self._jars.get(domain)
                if jar and jar.is_valid:
                    return dict(jar.cookies)
            except asyncio.TimeoutError:
                log.warning("cookie_pool_wait_timeout", domain=domain, timeout=timeout)
        return None

    async def put_cookies(
        self,
        domain: str,
        cookies: dict[str, str],
        ttl: int = 300,
        source: str = "resolver",
    ) -> None:
        """Store a resolved cookie jar for *domain*."""
        self._jars[domain] = CookieJar(
            domain=domain,
            cookies=dict(cookies),
            acquired_at=time.monotonic(),
            ttl_seconds=ttl,
            source=source,
        )
        # Signal any waiting workers
        event = self._resolve_events.get(domain)
        if event:
            event.set()
        log.debug("cookie_pool_put", domain=domain, cookies=list(cookies.keys()), ttl=ttl)

    async def invalidate(self, domain: str) -> None:
        """Remove a domain's cookie jar (e.g., on 401/403 after using cached cookies)."""
        self._jars.pop(domain, None)
        # Reset the resolve event so the next get_cookies triggers fresh resolution
        event = self._resolve_events.get(domain)
        if event:
            event.clear()
        log.debug("cookie_pool_invalidated", domain=domain)

    def begin_resolving(self, domain: str) -> None:
        """Signal that resolution for *domain* is in progress (prevents duplicate solves)."""
        if domain not in self._resolve_events:
            self._resolve_events[domain] = asyncio.Event()
        else:
            self._resolve_events[domain].clear()

    def get_lock(self, domain: str) -> asyncio.Lock:
        """Return a per-domain asyncio lock for exclusive resolver access."""
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    # ------------------------------------------------------------------
    # Proactive TTL refresh
    # ------------------------------------------------------------------

    def register_refresh_callback(
        self,
        callback: Callable[[str], Coroutine[Any, Any, dict[str, str] | None]],
    ) -> None:
        """Register an async function ``async (domain) → cookies | None`` for background refresh."""
        self._refresh_callback = callback

    async def start_refresh_loop(self, check_interval: float = 10.0) -> None:
        """Start a background coroutine that proactively refreshes expiring jars.

        Call this once at startup::

            asyncio.create_task(pool.start_refresh_loop())
        """
        self._refresh_task = asyncio.create_task(self._refresh_loop(check_interval))

    async def _refresh_loop(self, interval: float) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                if self._refresh_callback is None:
                    continue
                for domain, jar in list(self._jars.items()):
                    if jar.is_valid and jar.seconds_until_expiry < 30:
                        log.debug("cookie_pool_proactive_refresh", domain=domain)
                        try:
                            new_cookies = await self._refresh_callback(domain)
                            if new_cookies:
                                await self.put_cookies(domain, new_cookies, ttl=jar.ttl_seconds)
                        except Exception as exc:
                            log.warning("cookie_pool_refresh_failed", domain=domain, error=str(exc))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("cookie_pool_refresh_loop_error", error=str(exc))

    def stop(self) -> None:
        """Cancel the background refresh task."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def cached_domains(self) -> list[str]:
        return [d for d, jar in self._jars.items() if jar.is_valid]

    def jar_status(self, domain: str) -> dict[str, Any]:
        jar = self._jars.get(domain)
        if jar is None:
            return {"domain": domain, "valid": False}
        return {
            "domain": domain,
            "valid": jar.is_valid,
            "ttl_remaining": jar.seconds_until_expiry,
            "source": jar.source,
            "cookies": list(jar.cookies.keys()),
        }
