from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # Playwright Page — avoid hard import; injected at runtime


# ---------------------------------------------------------------------------
# Generic challenge signals — no system-specific brand names.
# These keywords appear in pages that are blocking access regardless of which
# protection vendor is in use.
# ---------------------------------------------------------------------------

_BLOCKED_BODY_KEYWORDS: tuple[str, ...] = (
    "captcha",
    "verify you are human",
    "press and hold",
    "i am not a robot",
    "one moment",
    "checking your browser",
    "please wait",
    "access denied",
    "blocked",
    "robot check",
    "security check",
    "challenge",
    "verify your identity",
    "human verification",
)

_BLOCKED_TITLE_KEYWORDS: tuple[str, ...] = (
    "captcha",
    "verify",
    "access denied",
    "blocked",
    "security check",
    "challenge",
    "one moment",
    "please wait",
    "checking",
)

_BLOCKED_STATUS_CODES: frozenset[int] = frozenset({403, 429, 503})

_META_REFRESH_RE = re.compile(r'<meta[^>]+http-equiv=["\']refresh["\']', re.IGNORECASE)


@dataclass
class ChallengeState:
    """Snapshot of whether the current page is blocked or has passed the challenge."""

    is_blocked: bool
    is_resolved: bool
    confidence: float          # 0.0–1.0
    evidence: list[str] = field(default_factory=list)

    @property
    def is_unknown(self) -> bool:
        return not self.is_blocked and not self.is_resolved


class ChallengeMonitor:
    """Universal challenge state detector.

    Does NOT identify which protection system is in use — it only answers
    two questions:

    1. Is the current page/response blocking us right now?
    2. Has the challenge been resolved and can we proceed?

    Usage::

        monitor = ChallengeMonitor()
        monitor.attach(page)

        state = await monitor.wait_for_resolution(timeout=30.0)
        if state.is_resolved:
            cookies = await page.context.cookies()
    """

    def __init__(self) -> None:
        self._page: Any = None
        self._cookies_before: set[str] = set()
        self._resolution_event: asyncio.Event = asyncio.Event()
        self._last_state: ChallengeState | None = None
        self._response_statuses: list[int] = []

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def attach(self, page: Any) -> None:
        """Attach to a Playwright page and start listening for navigation events."""
        self._page = page
        page.on("response", self._on_response)
        page.on("framenavigated", self._on_navigation)

    def detach(self) -> None:
        """Detach from the Playwright page and clean up listeners."""
        if self._page:
            self._page.remove_listener("response", self._on_response)
            self._page.remove_listener("framenavigated", self._on_navigation)
            self._page = None

    def _on_response(self, response: Any) -> None:
        try:
            status = response.status
            if isinstance(status, int):
                self._response_statuses.append(status)
        except Exception:
            pass

    def _on_navigation(self, _frame: Any) -> None:
        # Signal that a navigation happened; callers re-check state
        pass

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    async def check(self, page: Any | None = None) -> ChallengeState:
        """Evaluate the current page state and return a ChallengeState."""
        target = page or self._page
        if target is None:
            return ChallengeState(is_blocked=False, is_resolved=False, confidence=0.0,
                                  evidence=["no page attached"])

        evidence: list[str] = []
        is_blocked = False

        # --- HTTP status codes ---
        for status in list(self._response_statuses):
            if status in _BLOCKED_STATUS_CODES:
                evidence.append(f"http_status_{status}")
                is_blocked = True

        # --- Page title ---
        try:
            title = (await target.title()).lower()
            for kw in _BLOCKED_TITLE_KEYWORDS:
                if kw in title:
                    evidence.append(f"title_contains:{kw}")
                    is_blocked = True
                    break
        except Exception:
            title = ""

        # --- Body text ---
        body_text = ""
        try:
            body_text = await target.evaluate("() => document.documentElement.innerText || ''")
            body_lower = body_text.lower()
            for kw in _BLOCKED_BODY_KEYWORDS:
                if kw in body_lower:
                    evidence.append(f"body_contains:{kw}")
                    is_blocked = True
                    break
        except Exception:
            pass

        # --- DOM innerHTML (catches JS-rendered challenges) ---
        dom_text = ""
        try:
            dom_text = await target.evaluate("() => document.documentElement.innerHTML || ''")
            if _META_REFRESH_RE.search(dom_text):
                evidence.append("meta_refresh_redirect")
                is_blocked = True
        except Exception:
            pass

        # --- Cookie delta: new cookies since attach → challenge resolved ---
        # Only trust cookies that look like session/challenge tokens; tracking/analytics
        # cookies (ads, pixels) can appear even on a still-blocked page and must be ignored.
        _CHALLENGE_COOKIE_HINTS: frozenset[str] = frozenset({
            "cf", "clearance", "session", "sess", "token", "auth",
            "pass", "challenge", "check", "verify", "captcha", "__id",
        })
        is_resolved = False
        try:
            current_cookies = {c["name"] for c in await target.context.cookies()}
            new_cookies = current_cookies - self._cookies_before
            if new_cookies and is_blocked:
                # Filter: only count cookies whose names hint at challenge resolution
                meaningful = {
                    name for name in new_cookies
                    if any(hint in name.lower() for hint in _CHALLENGE_COOKIE_HINTS)
                }
                if meaningful:
                    evidence.append(f"new_cookies:{','.join(sorted(meaningful))}")
                    is_resolved = True
                    is_blocked = False
        except Exception:
            pass

        # --- Normal page: no blocked signals → resolved ---
        # Bug-3 fix: only resolve if page has actual content (prevent empty/loading pages being
        # misclassified as resolved)
        if not is_blocked and not is_resolved:
            has_content = bool(title or (body_text and len(body_text.strip()) > 100))
            is_resolved = has_content

        confidence = min(1.0, 0.4 + len(evidence) * 0.2) if evidence else 0.8

        state = ChallengeState(
            is_blocked=is_blocked,
            is_resolved=is_resolved,
            confidence=confidence,
            evidence=evidence,
        )
        self._last_state = state
        return state

    async def snapshot_cookies(self, page: Any | None = None) -> None:
        """Record current cookie names as the pre-challenge baseline."""
        target = page or self._page
        if target is None:
            return
        try:
            self._cookies_before = {c["name"] for c in await target.context.cookies()}
        except Exception:
            self._cookies_before = set()

    # ------------------------------------------------------------------
    # Waiting
    # ------------------------------------------------------------------

    async def wait_for_resolution(
        self,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
        page: Any | None = None,
    ) -> ChallengeState:
        """Poll until the challenge is resolved or timeout is reached.

        Uses adaptive polling: 0.5s for the first 5 seconds (many JS challenges
        self-resolve quickly), then 1.5s thereafter to reduce CPU load.

        Returns the final ChallengeState. If timeout expires while still
        blocked, returns is_resolved=False with the last known evidence.
        """
        target = page or self._page
        deadline = asyncio.get_event_loop().time() + timeout
        fast_phase_end = asyncio.get_event_loop().time() + 5.0

        await self.snapshot_cookies(target)

        while True:
            state = await self.check(target)
            if state.is_resolved and not state.is_blocked:
                return state
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return ChallengeState(
                    is_blocked=state.is_blocked,
                    is_resolved=False,
                    confidence=state.confidence,
                    evidence=state.evidence + ["timeout"],
                )
            # Adaptive: fast polling for first 5s, then slower
            now = asyncio.get_event_loop().time()
            effective_interval = poll_interval if now < fast_phase_end else 1.5
            await asyncio.sleep(min(effective_interval, remaining))
