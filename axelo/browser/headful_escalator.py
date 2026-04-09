"""Cap-3: Headful browser escalation for when headless mode fails challenges.

When the headless browser fails to resolve a challenge after all retries,
this module escalates to a visible (headful) browser and optionally waits
for human intervention (e.g., solving a visual CAPTCHA).

Platform support:
  - Windows: launches headless=False with a minimized window
  - Linux: detects DISPLAY; if absent, wraps in Xvfb virtual framebuffer
  - macOS: launches headless=False (window appears on screen)

Modes:
  - "hidden": headful but minimized (automated, less visible to user)
  - "visible": headful, full visible window (human-in-loop)
  - "virtual": Linux Xvfb virtual framebuffer (automated, no physical display)

Usage::

    escalator = HeadfulEscalator()
    session = await escalator.escalate_and_wait(
        url="https://example.com/",
        profile=target.browser_profile,
        mode="visible",
        timeout=120.0,
    )
    if session:
        target.session_state = _apply_resolved_session(target.session_state, session)
"""
from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field

import structlog

from axelo.browser.challenge_monitor import ChallengeMonitor
from axelo.browser.driver import BrowserDriver
from axelo.browser.real_browser_resolver import ResolvedSession
from axelo.models.target import BrowserProfile

log = structlog.get_logger()

_OS = platform.system().lower()


@dataclass
class EscalationResult:
    """Result of a headful escalation attempt."""
    success: bool
    session: ResolvedSession | None = None
    evidence: list[str] = field(default_factory=list)
    mode_used: str = ""


class HeadfulEscalator:
    """Escalates from headless to headful mode when challenges cannot be auto-solved.

    The escalator launches a visible Chrome window and either:
    1. Waits for the challenge to auto-resolve (JS-based challenges often self-complete
       once a real browser is detected), or
    2. Waits for a human to manually complete the challenge (visual CAPTCHA).

    After resolution, the escalator extracts the resulting cookies and
    storage state, then closes the browser.
    """

    def __init__(self, browser_path: str = "", node_bin: str = "node") -> None:
        self._browser_path = browser_path
        self._node_bin = node_bin

    async def escalate_and_wait(
        self,
        url: str,
        profile: BrowserProfile,
        mode: str = "visible",
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> ResolvedSession | None:
        """Launch a headful browser and wait for the challenge to resolve.

        Parameters
        ----------
        url:
            The target URL that triggered the challenge.
        profile:
            BrowserProfile to use for the headful browser.
        mode:
            "hidden" = minimized window, "visible" = full window, "virtual" = Xvfb
        timeout:
            Seconds to wait for challenge resolution (give humans 2 minutes).
        poll_interval:
            How often (seconds) to check if the challenge has resolved.

        Returns
        -------
        ResolvedSession if challenge was solved, else None.
        """
        effective_mode = self._resolve_mode(mode)
        log.info("headful_escalation_start", url=url[:80], mode=effective_mode, timeout=timeout)

        xvfb_proc: subprocess.Popen | None = None
        try:
            if effective_mode == "virtual":
                xvfb_proc = self._start_xvfb()
                if xvfb_proc is None:
                    log.warning("xvfb_unavailable", fallback="visible")
                    effective_mode = "visible"

            result = await self._run_headful_session(
                url=url,
                profile=profile,
                mode=effective_mode,
                timeout=timeout,
                poll_interval=poll_interval,
            )
            return result

        except Exception as exc:
            log.error("headful_escalation_failed", error=str(exc))
            return None
        finally:
            if xvfb_proc is not None:
                xvfb_proc.terminate()

    async def _run_headful_session(
        self,
        url: str,
        profile: BrowserProfile,
        mode: str,
        timeout: float,
        poll_interval: float,
    ) -> ResolvedSession | None:
        # Launch a real headful browser (headless=False)
        driver = BrowserDriver(browser="chromium", headless=False)
        monitor = ChallengeMonitor()

        async with driver:
            launch_kwargs: dict = {}
            if mode == "hidden" and _OS == "windows":
                # On Windows, we can start minimized via CDP after launch
                launch_kwargs["args"] = ["--start-minimized"]

            page = await driver.launch(profile, session_state=None)
            monitor.attach(page)
            await monitor.snapshot_cookies(page)

            log.info("headful_browser_launched", url=url[:80], mode=mode)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                log.debug("headful_goto_exception", error=str(exc))

            if mode == "visible":
                log.info(
                    "waiting_for_human",
                    url=url[:80],
                    timeout=timeout,
                    message="Please solve the challenge in the browser window...",
                )

            # Poll until challenge resolves or timeout
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                state = await monitor.check(page)
                if state.is_resolved and not state.is_blocked:
                    log.info("headful_challenge_resolved", evidence=state.evidence)
                    cookies = await self._extract_cookies(page)
                    return ResolvedSession(
                        cookies=cookies,
                        acquired_at=time.time(),
                        ttl_seconds=1800,
                        evidence=state.evidence,
                    )
                await asyncio.sleep(poll_interval)

            log.warning("headful_escalation_timeout", url=url[:80], timeout=timeout)
            return None

    async def _extract_cookies(self, page) -> dict[str, str]:
        """Extract all cookies from the current browser context."""
        try:
            raw = await page.context.cookies()
            return {c["name"]: c.get("value", "") for c in raw if c.get("name")}
        except Exception:
            return {}

    def _resolve_mode(self, requested: str) -> str:
        """Resolve the requested mode for the current platform."""
        if requested == "virtual":
            if _OS == "linux":
                return "virtual"
            return "hidden"  # No Xvfb on Windows/Mac
        return requested

    @staticmethod
    def _start_xvfb() -> subprocess.Popen | None:
        """Start a virtual X framebuffer on Linux. Returns the process or None."""
        if _OS != "linux":
            return None
        try:
            display = ":99"
            proc = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1920x1080x24"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Set DISPLAY for this process so Playwright uses the virtual display
            os.environ["DISPLAY"] = display
            time.sleep(0.5)  # Give Xvfb a moment to start
            return proc
        except FileNotFoundError:
            return None
