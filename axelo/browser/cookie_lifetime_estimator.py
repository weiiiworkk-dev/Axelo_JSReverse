from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class CookieLifetimeEstimator:
    """Estimate a cookie's useful lifetime in seconds without naming specific blue-team systems.

    Priority:
    1. Explicit Max-Age / Expires attributes  → use the actual value
    2. Cookie name matches a known pattern    → use a conservative preset
    3. Fallback                               → 120 seconds
    """

    # (substring, ttl_seconds) — matched case-insensitively against cookie name
    _NAME_PATTERNS: tuple[tuple[str, int], ...] = (
        ("clearance", 25 * 60),       # challenge-clearance tokens typically last ~30min; use 25min
        ("abck", 90),                 # accelerated-bot-check cookies are short-lived
        ("px3", 120),
        ("pxhd", 120),
        ("session", 30 * 60),
        ("sess", 30 * 60),
        ("token", 10 * 60),
        ("tmp", 60),
        ("temp", 60),
    )

    _DEFAULT_TTL = 120

    def estimate(self, cookie_name: str, cookie_attrs: dict[str, Any] | None = None) -> int:
        """Return a recommended cache TTL in seconds for the given cookie.

        Parameters
        ----------
        cookie_name:
            The bare cookie name (e.g. ``"cf_clearance"``).
        cookie_attrs:
            Optional dict that may contain ``"max_age"`` (int), ``"expires"``
            (datetime or ISO-8601 str), or ``"expires_at"`` (same).
        """
        attrs = cookie_attrs or {}

        # 1. Honour explicit Max-Age
        max_age = attrs.get("max_age") or attrs.get("maxAge")
        if max_age is not None:
            try:
                ttl = int(max_age)
                if ttl > 0:
                    return ttl
            except (TypeError, ValueError):
                pass

        # 2. Honour explicit Expires
        expires = attrs.get("expires") or attrs.get("expires_at") or attrs.get("expiresAt")
        if expires is not None:
            try:
                if isinstance(expires, str):
                    expires = datetime.fromisoformat(expires)
                if isinstance(expires, datetime):
                    now = datetime.now(tz=timezone.utc)
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    remaining = int((expires - now).total_seconds())
                    if remaining > 0:
                        return remaining
            except Exception:
                pass

        # 3. Match against name patterns
        name_lower = cookie_name.lower()
        for pattern, ttl in self._NAME_PATTERNS:
            if pattern in name_lower:
                return ttl

        return self._DEFAULT_TTL
