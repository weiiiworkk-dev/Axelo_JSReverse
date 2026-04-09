from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import structlog

from axelo.browser.challenge_monitor import ChallengeMonitor
from axelo.browser.cookie_lifetime_estimator import CookieLifetimeEstimator

if TYPE_CHECKING:
    from axelo.models.session_state import SessionState
    from axelo.models.target import BrowserProfile

log = structlog.get_logger()


@dataclass
class ResolvedSession:
    """Result of a successful challenge resolution via real browser."""

    cookies: dict[str, str]         # name → value mapping
    storage_state: dict             # Playwright storage_state snapshot
    acquired_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    ttl_seconds: int = 120          # conservative cache validity estimate
    evidence: list[str] = field(default_factory=list)


class RealBrowserResolver:
    """Universal challenge resolver that uses a real Playwright browser.

    Does NOT implement system-specific bypass logic. Instead it relies on the
    principle that any JS challenge will naturally complete inside a real
    browser with realistic fingerprints. All that's needed is:

    1. Navigate with a properly configured browser (FingerprintEngine injected).
    2. Wait for the challenge to resolve via ChallengeMonitor.
    3. Harvest the resulting Cookie Jar.

    This approach handles every challenge system — including unknown ones —
    without any system-specific code.
    """

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._estimator = CookieLifetimeEstimator()

    async def resolve(
        self,
        url: str,
        profile: "BrowserProfile",
        existing_session: "SessionState | None" = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> ResolvedSession | None:
        """Navigate to *url* and wait for any challenge to resolve.

        Parameters
        ----------
        url:
            The target URL that may present a challenge.
        profile:
            Browser fingerprint profile (used to inject simulation fixtures).
        existing_session:
            An existing SessionState whose cookies/storage-state will be
            pre-loaded into the browser context.
        timeout:
            Maximum seconds to wait per attempt for the challenge to resolve.
        max_retries:
            Number of navigation attempts before giving up.

        Returns
        -------
        ResolvedSession or None
            ``None`` means the challenge could not be resolved automatically.
        """
        from axelo.browser.driver import BrowserDriver

        for attempt in range(1, max_retries + 1):
            log.info("real_browser_resolve_attempt", url=url[:120], attempt=attempt, max_retries=max_retries)
            result = await self._attempt(url, profile, existing_session, timeout)
            if result is not None:
                log.info("real_browser_resolve_success", url=url[:120], attempt=attempt,
                         cookies=list(result.cookies.keys()))
                return result
            log.warning("real_browser_resolve_failed", url=url[:120], attempt=attempt)
            if attempt < max_retries:
                await asyncio.sleep(2.0)

        return None

    async def _attempt(
        self,
        url: str,
        profile: "BrowserProfile",
        existing_session: "SessionState | None",
        timeout: float,
    ) -> ResolvedSession | None:
        from axelo.browser.driver import BrowserDriver

        driver = BrowserDriver(headless=self._headless)
        try:
            page = await driver.launch(profile=profile, session_state=existing_session)
            monitor = ChallengeMonitor()
            monitor.attach(page)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception as exc:
                log.warning("real_browser_navigation_error", error=str(exc)[:200])

            state = await monitor.wait_for_resolution(timeout=timeout, page=page)

            if not state.is_resolved or state.is_blocked:
                log.warning("challenge_not_resolved", evidence=state.evidence)
                return None

            # Harvest cookies
            raw_cookies: list[dict[str, Any]] = await page.context.cookies()
            cookies = {c["name"]: c["value"] for c in raw_cookies if c.get("name")}

            # Estimate minimum TTL across harvested cookies
            ttls = [self._estimator.estimate(name, c) for c, name in
                    ((c, c["name"]) for c in raw_cookies if c.get("name"))]
            ttl = min(ttls) if ttls else 120

            storage_state: dict = {}
            try:
                storage_state = await driver.export_storage_state()
            except Exception:
                pass

            return ResolvedSession(
                cookies=cookies,
                storage_state=storage_state,
                ttl_seconds=ttl,
                evidence=state.evidence,
            )
        except Exception as exc:
            log.error("real_browser_resolve_exception", error=str(exc)[:300])
            return None
        finally:
            try:
                await driver.close()
            except Exception as _close_exc:
                log.warning("real_browser_resolver_close_failed", error=str(_close_exc)[:200])
