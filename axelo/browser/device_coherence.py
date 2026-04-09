"""Device fingerprint coherence validator.

Anti-bot systems (DataDome, PerimeterX, Akamai) cross-check device signals:
a macOS + Apple Silicon profile that reports an ANGLE/Intel WebGL renderer is
internally inconsistent and flags as synthetic.

This module validates BrowserProfile snapshots against universal OS↔GPU↔API
coherence rules (no site-specific logic), reporting violations so callers can
auto-repair or downrank the profile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoherenceViolation:
    field: str
    expected: str
    actual: str
    reason: str


# ---------------------------------------------------------------------------
# Coherence rule table: (os_keyword, gpu_keyword, expected_renderer_prefix)
# All checks are case-insensitive substring matches.
# ---------------------------------------------------------------------------
_RENDERER_RULES: list[tuple[str, str, str]] = [
    # macOS + Apple Silicon should use Metal, not ANGLE/Intel/NVIDIA
    ("macos",   "apple",  "ANGLE (Apple"),
    ("macintel","apple",  "ANGLE (Apple"),
    # macOS + Intel should use OpenGL Engine or ANGLE/Intel, NOT Metal
    ("macos",   "intel inc.", "ANGLE (Intel Inc."),
    ("macintel","intel inc.", "ANGLE (Intel Inc."),
    # Windows + NVIDIA should use Direct3D11
    ("win32",   "nvidia", "ANGLE (NVIDIA"),
    # Windows + AMD should use Direct3D11
    ("win32",   "amd",    "ANGLE (AMD"),
    # Windows + Intel should use Direct3D11
    ("win32",   "intel",  "ANGLE (Intel"),
    # Linux should use Mesa or ANGLE/Mesa
    ("linux",   "",       "ANGLE ("),   # broadly valid
]

# Vendor → renderer partial match rules (renderer must contain vendor hint)
_VENDOR_RENDERER_COHERENCE: list[tuple[str, str]] = [
    ("nvidia",      "nvidia"),
    ("amd",         "amd"),
    ("intel inc.",  "intel"),
    ("intel",       "intel"),
    ("apple",       "apple"),
    ("mesa",        "mesa"),
]


def validate_profile_coherence(
    platform: str,
    webgl_vendor: str,
    webgl_renderer: str,
    user_agent: str = "",
) -> list[CoherenceViolation]:
    """Check whether the device fingerprint fields are internally consistent.

    Parameters
    ----------
    platform:         JS ``navigator.platform`` value (e.g. "Win32", "MacIntel")
    webgl_vendor:     ``WEBGL_debug_renderer_info`` unmasked vendor string
    webgl_renderer:   ``WEBGL_debug_renderer_info`` unmasked renderer string
    user_agent:       Full UA string (used for additional OS cross-checks)

    Returns a list of CoherenceViolation objects.  Empty list = coherent profile.
    """
    violations: list[CoherenceViolation] = []
    platform_l = platform.strip().lower()
    vendor_l = webgl_vendor.strip().lower()
    renderer_l = webgl_renderer.strip().lower()
    ua_l = user_agent.strip().lower()

    # --- Vendor ↔ Renderer coherence ---
    for vendor_kw, renderer_kw in _VENDOR_RENDERER_COHERENCE:
        if vendor_kw in vendor_l and renderer_kw not in renderer_l:
            violations.append(CoherenceViolation(
                field="webgl_renderer",
                expected=f"contains '{renderer_kw}'",
                actual=webgl_renderer,
                reason=f"vendor '{webgl_vendor}' implies renderer should contain '{renderer_kw}'",
            ))

    # --- Apple Silicon: Metal only ---
    if "apple" in vendor_l and "apple m" in renderer_l and "angle (apple" not in renderer_l:
        violations.append(CoherenceViolation(
            field="webgl_renderer",
            expected="ANGLE (Apple, ANGLE Metal Renderer: Apple M…)",
            actual=webgl_renderer,
            reason="Apple Silicon GPU must use ANGLE Metal renderer",
        ))

    # --- UA OS ↔ platform coherence ---
    if ua_l:
        if "windows" in ua_l and platform_l not in ("win32", "win64"):
            violations.append(CoherenceViolation(
                field="platform",
                expected="Win32 or Win64",
                actual=platform,
                reason="UA declares Windows but platform does not",
            ))
        if "macintosh" in ua_l and "mac" not in platform_l:
            violations.append(CoherenceViolation(
                field="platform",
                expected="MacIntel or MacPPC",
                actual=platform,
                reason="UA declares Macintosh but platform does not",
            ))
        if "linux" in ua_l and "win" in platform_l:
            violations.append(CoherenceViolation(
                field="platform",
                expected="Linux x86_64 or similar",
                actual=platform,
                reason="UA declares Linux but platform is Windows",
            ))

    # --- Direct3D11 must only appear on Windows ---
    if "direct3d11" in renderer_l and "win" not in platform_l:
        violations.append(CoherenceViolation(
            field="webgl_renderer",
            expected="OpenGL or Metal renderer on non-Windows",
            actual=webgl_renderer,
            reason="Direct3D11 renderer is Windows-only; non-Windows platform is inconsistent",
        ))

    return violations


def auto_repair_renderer(
    platform: str,
    webgl_vendor: str,
    webgl_renderer: str,
) -> str:
    """Best-effort auto-repair: return a plausible renderer string for this platform+vendor.

    Returns the original renderer when no repair is possible.
    """
    platform_l = platform.strip().lower()
    vendor_l = webgl_vendor.strip().lower()

    if "apple" in vendor_l:
        if "m3" in vendor_l or "m2" in vendor_l or "m1" in vendor_l:
            chip = "Apple M1"
            for chip_kw in ("M3", "M2", "M1 Pro", "M1 Max", "M1"):
                if chip_kw.lower() in vendor_l:
                    chip = f"Apple {chip_kw}"
                    break
            return f"ANGLE (Apple, ANGLE Metal Renderer: {chip}, Unspecified Version)"
        return "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)"

    if "nvidia" in vendor_l:
        if "win" in platform_l:
            return "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"
        return "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1060/PCIe/SSE2, OpenGL 4.6.0)"

    if "amd" in vendor_l:
        if "win" in platform_l:
            return "ANGLE (AMD, AMD Radeon RX 6600 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"

    if "intel" in vendor_l:
        if "win" in platform_l:
            return "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"
        if "mac" in platform_l:
            return "ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics OpenGL Engine, OpenGL 4.1)"
        return "ANGLE (Mesa, Mesa Intel(R) UHD Graphics 620 (WHL GT2), OpenGL 4.6 (Core Profile) Mesa 23.0.4)"

    return webgl_renderer  # no repair possible
