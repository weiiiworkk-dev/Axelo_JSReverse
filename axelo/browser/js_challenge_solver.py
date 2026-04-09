"""Cap-7: Lightweight JS challenge self-solver (no full browser required).

Attempts to solve common challenge patterns using pure Python / curl_cffi,
before falling back to the heavyweight RealBrowserResolver.

Supported challenge types:
  Type-1: Cookie timestamp validation — extract time-token from Set-Cookie, re-send within deadline
  Type-2: JS-computed cookie — extract simple inline <script> and eval via Node.js sandbox
  Type-3: Redirect chain tracking — follow 302 chains and collect Set-Cookie headers

On success, returns a dict of new cookies.  On failure, returns None (caller falls back to RealBrowserResolver).
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from typing import Any

import structlog

log = structlog.get_logger()

# Regex patterns for lightweight detection (generic, no system-specific strings)
_SET_COOKIE_RE = re.compile(r'Set-Cookie:\s*([^;\r\n]+)', re.IGNORECASE)
_TIMESTAMP_COOKIE_RE = re.compile(r'(\w+)=(\d{10,13})')
_SCRIPT_COOKIE_RE = re.compile(
    r'<script[^>]*>.*?document\.cookie\s*=\s*["\']([^"\']+)["\'].*?</script>',
    re.IGNORECASE | re.DOTALL,
)
_REDIRECT_RE = re.compile(r'^3\d{2}$')


class JSChallengeSolver:
    """Lightweight challenge solver — ~0 browser overhead for solved cases.

    Usage::

        solver = JSChallengeSolver()
        new_cookies = await solver.try_solve(
            url="https://example.com/",
            response_headers={"set-cookie": "ts=1714000000; Path=/"},
            response_body="",
            existing_cookies={},
        )
        if new_cookies:
            # challenge solved, merge cookies and retry
            ...
    """

    def __init__(self, node_bin: str = "node", timeout: float = 5.0) -> None:
        self._node_bin = node_bin
        self._timeout = timeout

    async def try_solve(
        self,
        url: str,
        response_headers: dict[str, str],
        response_body: str,
        existing_cookies: dict[str, str],
    ) -> dict[str, str] | None:
        """Attempt lightweight challenge solving. Returns new cookies or None."""
        # Try each solver in order from cheapest to most expensive
        result = await self._solve_redirect_chain(url, existing_cookies)
        if result is not None:
            log.info("challenge_solved_redirect_chain", url=url[:80], cookies=list(result.keys()))
            return result

        result = self._solve_timestamp_cookie(response_headers, existing_cookies)
        if result is not None:
            log.info("challenge_solved_timestamp_cookie", url=url[:80], cookies=list(result.keys()))
            return result

        result = await self._solve_js_cookie(response_body, existing_cookies)
        if result is not None:
            log.info("challenge_solved_js_cookie", url=url[:80], cookies=list(result.keys()))
            return result

        return None

    # ------------------------------------------------------------------
    # Type-1: Cookie timestamp validation
    # ------------------------------------------------------------------

    def _solve_timestamp_cookie(
        self,
        response_headers: dict[str, str],
        existing_cookies: dict[str, str],
    ) -> dict[str, str] | None:
        """Detect and solve time-limited cookie challenges.

        Some systems set a cookie containing the current Unix timestamp
        and validate that the client returns it within N seconds.
        """
        set_cookie = response_headers.get("set-cookie", "")
        if not set_cookie:
            return None

        new_cookies: dict[str, str] = {}
        for match in _TIMESTAMP_COOKIE_RE.finditer(set_cookie):
            name, ts_str = match.group(1), match.group(2)
            ts = int(ts_str)
            # Is this a timestamp that's close to now? (within 120 seconds)
            now = int(time.time())
            ts_seconds = ts if ts < 10_000_000_000 else ts // 1000
            if abs(now - ts_seconds) <= 120:
                new_cookies[name] = ts_str

        return new_cookies if new_cookies else None

    # ------------------------------------------------------------------
    # Type-2: JS-computed cookie (Node.js sandbox)
    # ------------------------------------------------------------------

    async def _solve_js_cookie(
        self,
        response_body: str,
        existing_cookies: dict[str, str],
    ) -> dict[str, str] | None:
        """Extract and evaluate simple document.cookie assignments via Node.js."""
        if not response_body:
            return None

        match = _SCRIPT_COOKIE_RE.search(response_body)
        if not match:
            return None

        cookie_str = match.group(1)
        if not cookie_str or "=" not in cookie_str:
            return None

        # Build a minimal Node.js script to evaluate the cookie expression
        js_code = f"""
const document = {{ cookie: '' }};
const navigator = {{ userAgent: 'Mozilla/5.0' }};
try {{
  document.cookie = {json.dumps(cookie_str)};
  process.stdout.write(document.cookie);
}} catch(e) {{
  process.stdout.write('');
}}
"""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: subprocess.run(
                        [self._node_bin, "-e", js_code],
                        capture_output=True,
                        text=True,
                        timeout=self._timeout,
                    )
                ),
                timeout=self._timeout + 1,
            )
            if result.returncode != 0 or not result.stdout:
                return None

            new_cookies = _parse_cookie_string(result.stdout)
            return new_cookies if new_cookies else None
        except (FileNotFoundError, asyncio.TimeoutError, Exception):
            return None

    # ------------------------------------------------------------------
    # Type-3: Redirect chain tracking
    # ------------------------------------------------------------------

    async def _solve_redirect_chain(
        self,
        url: str,
        existing_cookies: dict[str, str],
    ) -> dict[str, str] | None:
        """Follow redirect chain and collect all Set-Cookie headers.

        Some challenges are purely redirect-based: the server sets
        challenge cookies through a 302 chain before returning to the
        original page.
        """
        try:
            import curl_cffi.requests as cr_requests  # type: ignore[import]
        except ImportError:
            try:
                import httpx as cr_requests  # type: ignore[import, no-redef]
            except ImportError:
                return None

        try:
            cookie_header = "; ".join(f"{k}={v}" for k, v in existing_cookies.items())
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            if cookie_header:
                headers["Cookie"] = cookie_header

            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: cr_requests.get(
                        url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=self._timeout,
                        impersonate="chrome124" if hasattr(cr_requests, "get") else None,
                    )
                ),
                timeout=self._timeout + 1,
            )
            # Collect all cookies set during the redirect chain
            new_cookies: dict[str, str] = {}
            if hasattr(resp, "cookies"):
                for name, value in resp.cookies.items():
                    if name not in existing_cookies:
                        new_cookies[name] = value
            return new_cookies if new_cookies else None
        except Exception:
            return None


def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    """Parse 'name=value; name2=value2' into a dict."""
    cookies: dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            cookies[name.strip()] = value.strip()
    return cookies
