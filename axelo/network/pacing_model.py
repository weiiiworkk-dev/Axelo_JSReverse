"""Cap-6: Human request pacing model.

Injects statistically realistic delays between browser actions to mimic
natural human browsing rhythm. Uses exponential and normal distributions
parameterized from real user behavior research.

Usage::

    pacing = RequestPacingModel(seed=12345)
    await pacing.before_navigation("https://example.com/search")
    # browser navigates...
    await pacing.after_page_load(load_time_ms=1200)
    await pacing.before_click("button")
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass

import structlog

log = structlog.get_logger()


@dataclass
class PacingConfig:
    """Tune-able parameters for the pacing model."""
    # Pre-navigation delay range (seconds, uniform)
    nav_delay_min: float = 0.5
    nav_delay_max: float = 5.0
    # Post-load reading time (seconds, lognormal)
    read_time_mean: float = 8.0
    read_time_std: float = 4.0
    read_time_min: float = 1.0
    read_time_max: float = 45.0
    # Pre-click reaction time (seconds, exponential)
    click_reaction_mean: float = 0.6
    click_reaction_min: float = 0.15
    click_reaction_max: float = 3.0
    # Maximum requests per minute per domain
    max_rpm: int = 30
    # Speed multiplier: 1.0 = real-time, 0.0 = instant
    speed_factor: float = 1.0


class RequestPacingModel:
    """Controls inter-request timing to match human browsing patterns.

    When ``speed_factor=0.0`` all delays are skipped (test / dev mode).
    When ``speed_factor=1.0`` full realistic delays are applied.
    Values between 0.0 and 1.0 scale delays proportionally.
    """

    def __init__(
        self,
        seed: int | None = None,
        config: PacingConfig | None = None,
        speed_factor: float = 1.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._config = config or PacingConfig(speed_factor=speed_factor)
        self._config.speed_factor = speed_factor
        self._domain_timestamps: dict[str, list[float]] = {}
        self._last_nav_ts: float = 0.0
        # Dynamic rate: reduced on 429, gradually restored on success
        self._rate_multiplier: float = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def before_navigation(self, url: str) -> None:
        """Wait before navigating to a URL (simulates user think time)."""
        domain = self._domain_from_url(url)
        await self._enforce_rate_limit(domain)

        delay = self._rng.uniform(
            self._config.nav_delay_min,
            self._config.nav_delay_max,
        )
        await self._sleep(delay * self._rate_multiplier)
        self._record_request(domain)

    async def before_click(self, element_type: str = "button") -> None:
        """Wait before clicking an element (simulates visual reaction time)."""
        mean = self._config.click_reaction_mean
        # Buttons: faster; links: slightly slower
        if "link" in element_type.lower():
            mean *= 1.2
        delay = self._rng.expovariate(1.0 / mean)
        delay = max(self._config.click_reaction_min, min(self._config.click_reaction_max, delay))
        await self._sleep(delay)

    async def after_page_load(self, load_time_ms: int = 0) -> None:
        """Wait for realistic reading time after a page loads.

        Users tend to spend more time reading after fast loads (they have time to read)
        and less after slow loads (they've already been waiting).
        """
        # Base reading time: lognormal distribution
        mu = math.log(max(1.0, self._config.read_time_mean))
        sigma = math.log(max(1.0, self._config.read_time_std + 1))
        delay = self._rng.lognormvariate(mu, sigma * 0.5)
        delay = max(self._config.read_time_min, min(self._config.read_time_max, delay))

        # Reduce reading time if page was slow to load (user already waited)
        if load_time_ms > 3000:
            delay *= max(0.3, 1.0 - (load_time_ms - 3000) / 10000)

        await self._sleep(delay)

    async def before_scroll(self) -> None:
        """Short pause before a scroll action."""
        delay = self._rng.uniform(0.2, 1.2)
        await self._sleep(delay)

    def on_rate_limited(self) -> None:
        """Call when a 429 response is received — reduces pacing speed."""
        self._rate_multiplier = max(0.1, self._rate_multiplier * 0.5)
        log.info("pacing_rate_limited", new_multiplier=f"{self._rate_multiplier:.2f}")

    def on_success(self) -> None:
        """Call on successful responses — gradually restores normal speed."""
        if self._rate_multiplier < 1.0:
            self._rate_multiplier = min(1.0, self._rate_multiplier * 1.1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sleep(self, seconds: float) -> None:
        """Sleep for *seconds* scaled by speed_factor."""
        effective = seconds * self._config.speed_factor
        if effective > 0.001:
            await asyncio.sleep(effective)

    async def _enforce_rate_limit(self, domain: str) -> None:
        """Block until the per-domain rate limit allows another request."""
        if self._config.max_rpm <= 0 or self._config.speed_factor == 0.0:
            return
        window = 60.0
        max_in_window = self._config.max_rpm
        now = time.monotonic()
        timestamps = self._domain_timestamps.get(domain, [])
        # Prune old timestamps
        timestamps = [ts for ts in timestamps if now - ts < window]
        if len(timestamps) >= max_in_window:
            # Wait until the oldest request falls outside the window
            oldest = timestamps[0]
            wait = window - (now - oldest) + 0.1
            if wait > 0:
                log.debug("pacing_rate_limit_wait", domain=domain, wait=f"{wait:.1f}s")
                await self._sleep(wait)
        self._domain_timestamps[domain] = timestamps

    def _record_request(self, domain: str) -> None:
        now = time.monotonic()
        self._domain_timestamps.setdefault(domain, []).append(now)
        self._last_nav_ts = now

    @staticmethod
    def _domain_from_url(url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc or url
        except Exception:
            return url
