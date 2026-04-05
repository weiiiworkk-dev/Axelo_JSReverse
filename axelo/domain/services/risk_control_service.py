from __future__ import annotations


class RiskControlService:
    # Taobao / Lazada / Alibaba group signals (challenge page and validation)
    CHALLENGE_SIGNALS = ("x5secdata", "/_____tmd_____/punish")
    VALIDATION_SIGNALS = ("rgv587_error", "fail_sys_user_validate")

    # Cloudflare — challenge page titles, cookie hints, and error page paths
    CLOUDFLARE_SIGNALS = (
        "just a moment",          # CF challenge page title
        "cloudflare ray id",      # CF error page footer
        "checking your browser",  # CF interstitial copy
        "/cdn-cgi/challenge-platform",
        "cf_clearance",           # CF clearance cookie name appearing in error pages
        "error 1020",             # CF access denied
        "error 1015",             # CF rate limit
    )

    # PerimeterX
    PERIMETERX_SIGNALS = (
        "_pxmvid",
        "px-captcha",
        "perimeterx",
        "/_px/",
        "/px/",
    )

    # Akamai Bot Manager
    AKAMAI_SIGNALS = (
        "akamai",
        "bm_sz",          # Akamai bot manager cookie
        "_abck",          # Akamai sensor data cookie
        "ak_bmsc",        # Akamai bot manager script cookie
    )

    # DataDome
    DATADOME_SIGNALS = (
        "datadome",
        "dd_cookie_test",
        "/tags.js?",      # DataDome tag path
    )

    # Generic HTTP-level block signals (URL patterns and status context)
    GENERIC_BLOCK_SIGNALS = (
        "access denied",
        "bot detected",
        "automated access",
        "suspicious activity",
    )

    def detect_text(self, *parts: str | None) -> str:
        signal_text = "\n".join(part for part in parts if part).lower()
        if not signal_text:
            return ""
        if any(signal in signal_text for signal in self.CHALLENGE_SIGNALS):
            return "risk-control challenge page detected"
        if any(signal in signal_text for signal in self.VALIDATION_SIGNALS):
            return "risk-control validation rejected the replay request"
        if any(signal in signal_text for signal in self.CLOUDFLARE_SIGNALS):
            return "cloudflare challenge or block detected"
        if any(signal in signal_text for signal in self.PERIMETERX_SIGNALS):
            return "perimeterx bot protection detected"
        if any(signal in signal_text for signal in self.AKAMAI_SIGNALS):
            return "akamai bot manager signal detected"
        if any(signal in signal_text for signal in self.DATADOME_SIGNALS):
            return "datadome bot protection detected"
        if any(signal in signal_text for signal in self.GENERIC_BLOCK_SIGNALS):
            return "generic bot-detection block signal detected"
        return ""

    def detect_replay(self, replay) -> str:
        return self.detect_text(getattr(replay, "response_body", ""), getattr(replay, "error", ""))
