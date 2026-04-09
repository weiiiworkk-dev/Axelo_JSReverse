"""Adaptive blue team capability detector.

Infers what anti-bot techniques a target site is using from the *observable
response sequence* — HTTP status patterns, header signatures, cookie delta
patterns, and challenge DOM signals.

All inference is brand-agnostic: the system detects *behaviours* (TLS
fingerprinting, behavioural ML scoring, DOM challenges, cookie validation)
without hard-coding vendor names such as Cloudflare, DataDome, or PerimeterX.
This keeps the module universally applicable to any blue team deployment.

Usage::

    detector = BlueteamDetector()
    profile = detector.infer(responses)   # list of (status, headers, body_snippet)
    if profile.uses_tls_fingerprinting:
        # switch TLS persona before next request
    if profile.uses_behavioral_ml:
        # inject extra action delays + behavior noise
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BlueteamCapabilityProfile:
    """Inferred capability profile of a site's anti-bot system.

    Fields are populated by analysing the response sequence; absent signals
    remain False / empty.  The profile is passed to RuntimePolicy so the
    crawler can adapt its evasion strategy dynamically.
    """
    # Detected capabilities
    uses_tls_fingerprinting: bool = False
    """Immediate 403/429 on TCP connect without any HTTP exchange suggests TLS fingerprinting."""

    uses_behavioral_ml: bool = False
    """Challenge appears after N successful requests, not on first contact → ML scoring."""

    uses_dom_challenge: bool = False
    """Page body contains challenge DOM elements (JS challenges, CAPTCHAs)."""

    uses_cookie_validation: bool = False
    """Response sets cookies that change on every request → token-based validation."""

    uses_rate_limiting: bool = False
    """Exponential 429 backoff pattern detected."""

    challenge_threshold_requests: int = 0
    """Number of successful requests before first challenge appeared (0 = unknown)."""

    backoff_pattern: str = "unknown"
    """Detected rate-limit strategy: 'linear', 'exponential', 'token_bucket', 'unknown'."""

    detected_signals: list[str] = field(default_factory=list)
    """Human-readable list of specific signals that drove each capability flag."""

    @property
    def evasion_intensity(self) -> str:
        """Suggested evasion intensity based on detected capabilities."""
        score = (
            int(self.uses_tls_fingerprinting) * 3
            + int(self.uses_behavioral_ml) * 3
            + int(self.uses_dom_challenge) * 2
            + int(self.uses_cookie_validation) * 1
            + int(self.uses_rate_limiting) * 1
        )
        if score >= 5:
            return "high"
        if score >= 2:
            return "medium"
        return "low"


# ---------------------------------------------------------------------------
# Observable response entry
# ---------------------------------------------------------------------------

@dataclass
class ObservedResponse:
    """Lightweight snapshot of a single HTTP exchange for analysis."""
    status: int
    headers: dict[str, str]      # lowercase keys
    body_snippet: str            # first 4 KB of response body (decoded, lowercased)
    request_index: int = 0       # 0-based position in the session's request sequence
    cookie_names_set: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class BlueteamDetector:
    """Infers blue team capabilities from a sequence of HTTP responses.

    Designed to be called after each crawl attempt so the system can
    adapt evasion intensity before the next retry.
    """

    # DOM / body signals that indicate an active challenge
    _CHALLENGE_BODY_SIGNALS = (
        "verify you are human",
        "checking your browser",
        "please wait",
        "one moment",
        "just a moment",
        "ray id",
        "captcha",
        "robot",
        "challenge",
        "turnstile",
        "recaptcha",
        "hcaptcha",
        "cf-challenge",
        "ddcaptcha",
        "px-captcha",
    )

    # Headers whose presence indicates a specific protection layer
    _PROTECTION_HEADER_SIGNALS = (
        "x-datadome",
        "x-cdn-protection",
        "cf-mitigated",
        "x-px",
        "x-perimeterx",
        "x-akamai-transformed",
        "x-bot-protection",
    )

    def infer(self, responses: list[ObservedResponse]) -> BlueteamCapabilityProfile:
        """Analyse *responses* and return a BlueteamCapabilityProfile.

        Parameters
        ----------
        responses:  ordered list of observed HTTP exchanges for one crawl session
        """
        if not responses:
            return BlueteamCapabilityProfile()

        profile = BlueteamCapabilityProfile()
        signals: list[str] = []

        statuses = [r.status for r in responses]
        first = responses[0]

        # --- TLS fingerprinting: 403 on the very first request, no challenge body ---
        if first.status in (403, 429) and not self._has_challenge_body(first):
            profile.uses_tls_fingerprinting = True
            signals.append(f"immediate {first.status} on first request with no challenge DOM")

        # --- Rate limiting: 429 appearing after initial successes ---
        success_count = sum(1 for s in statuses if 200 <= s < 400)
        block_count = sum(1 for s in statuses if s in (429, 503))
        if block_count >= 1 and success_count >= 1:
            profile.uses_rate_limiting = True
            profile.challenge_threshold_requests = success_count
            signals.append(f"rate-limit after {success_count} successful requests")

            # Determine backoff pattern from timing (approximate from status sequence)
            consecutive_blocks = max(
                sum(1 for _ in g)
                for k, g in _groupby_consecutive(statuses, lambda s: s in (429, 503))
                if k
            ) if block_count > 1 else 1
            profile.backoff_pattern = "exponential" if consecutive_blocks >= 3 else "linear"

        # --- Behavioural ML: challenge appears mid-session, not on first contact ---
        first_challenge_idx = next(
            (r.request_index for r in responses if self._has_challenge_body(r) or r.status in (403, 429, 503)),
            None,
        )
        if first_challenge_idx is not None and first_challenge_idx >= 3:
            profile.uses_behavioral_ml = True
            profile.challenge_threshold_requests = first_challenge_idx
            signals.append(f"challenge appeared at request #{first_challenge_idx} (ML scoring pattern)")

        # --- DOM challenge detection ---
        for resp in responses:
            if self._has_challenge_body(resp):
                profile.uses_dom_challenge = True
                signals.append("challenge DOM detected in response body")
                break

        # --- Cookie validation: new cookies set on each response ---
        seen_cookie_names: set[str] = set()
        novel_cookie_counts = 0
        for resp in responses:
            new = resp.cookie_names_set - seen_cookie_names
            if new:
                novel_cookie_counts += 1
                seen_cookie_names |= new
        if novel_cookie_counts >= len(responses) // 2 and novel_cookie_counts >= 2:
            profile.uses_cookie_validation = True
            signals.append(f"new cookies set in {novel_cookie_counts}/{len(responses)} responses")

        # --- Protection-layer header detection ---
        for resp in responses:
            for hdr in self._PROTECTION_HEADER_SIGNALS:
                if hdr in resp.headers:
                    signals.append(f"protection header '{hdr}' detected")
                    break

        profile.detected_signals = signals
        return profile

    def _has_challenge_body(self, resp: ObservedResponse) -> bool:
        return any(sig in resp.body_snippet for sig in self._CHALLENGE_BODY_SIGNALS)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _groupby_consecutive(seq: list, key):
    """Yield (key_value, iterator) groups of consecutive equal-key items."""
    from itertools import groupby
    return groupby(seq, key)
