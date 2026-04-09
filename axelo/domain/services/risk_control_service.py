from __future__ import annotations

import re
from collections.abc import Mapping


class RiskControlService:
    # DOM-level signals injected after JS execution (not present in raw HTML)
    JS_RENDERED_CHALLENGE_SIGNALS = (
        "cf-turnstile",
        "challenges.cloudflare.com",
        "__cf_chl_opt",         # Cloudflare JS challenge object
        "bmak.js_ver",          # Akamai sensor_data injection point
        "bmak.get_telemetry",
        "ddcaptcha",            # DataDome JS challenge
        "px-captcha",           # PerimeterX enforcer
        "_pxab",                # PerimeterX additional beacon
    )

    # URL path prefixes used by anti-bot systems for challenge redirects
    CHALLENGE_REDIRECT_PATHS = (
        "/cdn-cgi/challenge-platform/",
        "/cdn-cgi/l/chk_jschl",
        "/__ddns/",
        "/_incapsula_resource",
        "/ak_verify",
    )

    _META_REFRESH_RE = re.compile(r'<meta[^>]+http-equiv=["\']refresh["\']', re.IGNORECASE)

    CHALLENGE_SIGNALS = (
        "x5secdata",
        "/_____tmd_____/punish",
        "just a moment",
        "cf challenge",
        "cf-browser-verification",
        "challenge-platform",
        "turnstile",
        "captcha",
        "verify you are human",
        "press and hold",
        "datadome",
        "perimeterx",
        "_pxmvid",
        "/px/",
        "recaptcha",
        "g-recaptcha",
        "hcaptcha",
        "akamai bot manager",
        "bm_sz",
        "ak_bmsc",
        "_abck",
    )
    VALIDATION_SIGNALS = ("rgv587_error", "fail_sys_user_validate")
    CHALLENGE_HEADER_SIGNALS = (
        "cf-mitigated",
        "x-datadome",
        # "x-cdn" intentionally removed: many CDNs (Shopee SGW, etc.) set
        # "x-cdn: staticcache" on normal responses; this header alone is not
        # a reliable challenge signal and causes false positives.
        "server: cloudflare",
        "server: datadome",
    )
    CHALLENGE_COOKIE_SIGNALS = (
        "cf_clearance",
        "datadome",
        "_pxmvid",
        "_pxvid",
        "_px3",
        "bm_sz",
        "ak_bmsc",
        "_abck",
    )

    def detect_text(self, *parts: str | None) -> str:
        signal_text = "\n".join(part for part in parts if part).lower()
        if not signal_text:
            return ""
        if any(signal in signal_text for signal in self.CHALLENGE_SIGNALS):
            return "risk-control challenge page detected"
        if any(signal in signal_text for signal in self.VALIDATION_SIGNALS):
            return "risk-control validation rejected the replay request"
        return ""

    def detect_response(
        self,
        *,
        url: str = "",
        status_code: int | None = None,
        headers: Mapping[str, str] | None = None,
        body_text: str = "",
        title: str = "",
        error: str = "",
    ) -> str:
        normalized_headers = {str(key).lower(): str(value).lower() for key, value in (headers or {}).items()}
        header_blob = "\n".join(f"{key}: {value}" for key, value in normalized_headers.items())
        direct_match = self.detect_text(url, body_text, title, error, header_blob)
        if direct_match:
            return direct_match

        if url and self.detect_challenge_redirect(url):
            return "risk-control challenge redirect detected"

        set_cookie = normalized_headers.get("set-cookie", "")
        if any(signal in header_blob for signal in self.CHALLENGE_HEADER_SIGNALS):
            return "risk-control challenge page detected"
        if any(signal in set_cookie for signal in self.CHALLENGE_COOKIE_SIGNALS):
            return "risk-control challenge page detected"

        content_type = normalized_headers.get("content-type", "")
        is_html = "text/html" in content_type or "<html" in body_text.lower()
        blocked_status = status_code in {401, 403, 429, 503}
        if blocked_status and (is_html or title or body_text):
            return "risk-control challenge page detected"

        if is_html and body_text and self.detect_meta_refresh(body_text):
            return "risk-control meta-refresh interstitial detected"

        return ""

    def detect_js_rendered_challenge(self, page_dom_text: str) -> bool:
        """Detect anti-bot challenges that only appear after JavaScript execution.

        Call this with the *final* DOM text (e.g. ``page.evaluate('document.documentElement.innerHTML')``)
        rather than the raw HTTP response body.  Returns True when a JS-rendered
        challenge element is found.
        """
        lowered = page_dom_text.lower()
        return any(sig in lowered for sig in self.JS_RENDERED_CHALLENGE_SIGNALS)

    def detect_challenge_redirect(self, url: str) -> bool:
        """Return True if the URL points to a known anti-bot challenge redirect path."""
        url_lower = url.lower()
        return any(path in url_lower for path in self.CHALLENGE_REDIRECT_PATHS)

    def detect_meta_refresh(self, body_text: str) -> bool:
        """Return True if the page uses a meta-refresh redirect, common in JS challenge interstitials."""
        return bool(self._META_REFRESH_RE.search(body_text))

    def detect_replay(self, replay) -> str:
        return self.detect_response(
            status_code=getattr(replay, "status_code", None),
            headers=getattr(replay, "response_headers", None) or {},
            body_text=getattr(replay, "response_body", ""),
            error=getattr(replay, "error", ""),
        )
