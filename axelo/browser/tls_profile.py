"""TLS fingerprint diversification — maps browser UA to a matching curl_cffi impersonate target.

Modern anti-bot systems (Shopee, Lazada, Amazon) check JA3/JA3S TLS fingerprints.
A fixed impersonate setting leaks a single fingerprint across all sessions.
This module selects a TLS persona whose cipher suite / extension order matches the
advertised User-Agent, ensuring TLS + UA coherence.

No site-specific logic — all decisions are based on generic UA string parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TLSPersona:
    """Binding between a UA pattern, curl_cffi impersonate target, and matching sec-ch-ua."""
    impersonate: str
    sec_ch_ua: str
    sec_ch_ua_platform: str


# ---------------------------------------------------------------------------
# Persona table — ordered from most to least specific.
# curl_cffi impersonate names: chrome110, chrome116, chrome120, chrome124,
#                              firefox120, firefox121, safari17_0, safari17_2_1
# ---------------------------------------------------------------------------
_PERSONAS: list[tuple[re.Pattern, TLSPersona]] = [
    # Chrome 124
    (re.compile(r"Chrome/124", re.I), TLSPersona(
        impersonate="chrome124",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
    )),
    # Chrome 123
    (re.compile(r"Chrome/123", re.I), TLSPersona(
        impersonate="chrome120",
        sec_ch_ua='"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
    )),
    # Chrome 122
    (re.compile(r"Chrome/122", re.I), TLSPersona(
        impersonate="chrome120",
        sec_ch_ua='"Chromium";v="122", "Google Chrome";v="122", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
    )),
    # Chrome on Mac
    (re.compile(r"Macintosh.*Chrome/(\d+)", re.I), TLSPersona(
        impersonate="chrome124",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
    )),
    # Chrome on Linux
    (re.compile(r"X11.*Linux.*Chrome/(\d+)", re.I), TLSPersona(
        impersonate="chrome120",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Linux"',
    )),
    # Safari
    (re.compile(r"Safari/6\d\d", re.I), TLSPersona(
        impersonate="safari17_0",
        sec_ch_ua="",  # Safari does not send sec-ch-ua
        sec_ch_ua_platform="",
    )),
    # Firefox
    (re.compile(r"Firefox/(\d+)", re.I), TLSPersona(
        impersonate="firefox121",
        sec_ch_ua="",  # Firefox does not send sec-ch-ua
        sec_ch_ua_platform="",
    )),
]

# Default fallback when no pattern matches
_DEFAULT_PERSONA = TLSPersona(
    impersonate="chrome124",
    sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    sec_ch_ua_platform='"Windows"',
)


def select_tls_persona(ua_string: str) -> TLSPersona:
    """Return the TLS persona whose fingerprint is consistent with *ua_string*.

    The caller should use ``persona.impersonate`` as the curl_cffi ``impersonate``
    argument and inject ``persona.sec_ch_ua`` / ``persona.sec_ch_ua_platform`` as
    extra HTTP request headers so that the TLS cipher suite matches the advertised UA.
    """
    if not ua_string:
        return _DEFAULT_PERSONA
    for pattern, persona in _PERSONAS:
        if pattern.search(ua_string):
            return persona
    return _DEFAULT_PERSONA


def build_tls_extra_headers(ua_string: str) -> dict[str, str]:
    """Return browser-hint headers that match the TLS persona for *ua_string*.

    Inject these headers into every Playwright browser context (via ``set_extra_http_headers``)
    and into curl_cffi sessions so that sec-ch-ua, sec-ch-ua-platform, and sec-ch-ua-mobile
    are consistent with the TLS fingerprint.
    """
    persona = select_tls_persona(ua_string)
    headers: dict[str, str] = {}
    if persona.sec_ch_ua:
        headers["sec-ch-ua"] = persona.sec_ch_ua
    if persona.sec_ch_ua_platform:
        headers["sec-ch-ua-platform"] = persona.sec_ch_ua_platform
        headers["sec-ch-ua-mobile"] = "?0"
    return headers
