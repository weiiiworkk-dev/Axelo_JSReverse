"""Cap-1: BrowserProfile diversity pool — 20 real Chrome snapshots rotated by domain.

Prevents fingerprint cohort tracking by ensuring the same domain never sees
the same browser fingerprint twice within a short window.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axelo.browser.device_coherence import auto_repair_renderer, validate_profile_coherence
from axelo.models.target import BrowserProfile, EnvironmentSimulation, WebGLSimulation


@dataclass
class _ProfileEntry:
    """Internal record for one snapshot in the pool."""
    snapshot_id: str
    profile: BrowserProfile
    last_used_by: dict[str, float] = field(default_factory=dict)  # domain → unix ts
    use_count: int = 0
    success_count: int = 0
    fail_count: int = 0

    @property
    def health_score(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 1.0
        return self.success_count / total


# ---------------------------------------------------------------------------
# 20 real Chrome snapshots (Windows / Mac / Linux mix, common resolutions)
# ---------------------------------------------------------------------------

def _make_profile(
    ua: str,
    width: int,
    height: int,
    platform: str,
    webgl_vendor: str,
    webgl_renderer: str,
    locale: str = "zh-CN",
    timezone: str = "Asia/Shanghai",
    hardware_concurrency: int = 8,
    device_memory: int = 8,
) -> BrowserProfile:
    profile = BrowserProfile(
        user_agent=ua,
        viewport_width=width,
        viewport_height=height,
        locale=locale,
        timezone=timezone,
    )
    profile.environment_simulation = EnvironmentSimulation(
        profile_name="desktop",
        webgl=WebGLSimulation(
            unmasked_vendor=webgl_vendor,
            unmasked_renderer=webgl_renderer,
        ),
        color_scheme="light",
        reduced_motion="no-preference",
        is_mobile=False,
        has_touch=False,
    )
    profile.environment_simulation.media.hardware_concurrency = hardware_concurrency
    profile.environment_simulation.media.device_memory = device_memory
    return profile


_WIN_UA_124 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_WIN_UA_123 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
_WIN_UA_122 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
_MAC_UA_124 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_MAC_UA_123 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
_MAC_UA_122 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_LNX_UA_124 = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_POOL_DEFINITIONS: list[dict[str, Any]] = [
    # Windows 1080p — Intel
    dict(ua=_WIN_UA_124, width=1920, height=1080, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=16, device_memory=16),
    # Windows 1080p — NVIDIA
    dict(ua=_WIN_UA_124, width=1920, height=1080, platform="Win32",
         webgl_vendor="Google Inc. (NVIDIA)", webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=12, device_memory=16),
    # Windows 1440p — Intel
    dict(ua=_WIN_UA_123, width=2560, height=1440, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=8, device_memory=8),
    # Windows 1440p — AMD
    dict(ua=_WIN_UA_122, width=2560, height=1440, platform="Win32",
         webgl_vendor="Google Inc. (AMD)", webgl_renderer="ANGLE (AMD, AMD Radeon RX 6600 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=8, device_memory=16),
    # Windows 1920x1200
    dict(ua=_WIN_UA_124, width=1920, height=1200, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=8, device_memory=8),
    # Windows 1366x768
    dict(ua=_WIN_UA_123, width=1366, height=768, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) HD Graphics 520 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=4, device_memory=4),
    # Windows 1280x1024
    dict(ua=_WIN_UA_122, width=1280, height=1024, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=4, device_memory=8),
    # Mac 1440p Retina (logical pixels)
    dict(ua=_MAC_UA_124, width=1440, height=900, platform="MacIntel",
         webgl_vendor="Google Inc. (Apple)", webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
         locale="zh-CN", timezone="Asia/Shanghai", hardware_concurrency=8, device_memory=8),
    # Mac 1080p
    dict(ua=_MAC_UA_123, width=1920, height=1080, platform="MacIntel",
         webgl_vendor="Google Inc. (Intel Inc.)", webgl_renderer="ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics OpenGL Engine, OpenGL 4.1)",
         locale="zh-CN", timezone="Asia/Shanghai", hardware_concurrency=4, device_memory=8),
    # Mac 13-inch Retina
    dict(ua=_MAC_UA_122, width=1280, height=800, platform="MacIntel",
         webgl_vendor="Google Inc. (Apple)", webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
         locale="zh-CN", timezone="Asia/Shanghai", hardware_concurrency=8, device_memory=8),
    # Mac 16-inch
    dict(ua=_MAC_UA_124, width=1728, height=1117, platform="MacIntel",
         webgl_vendor="Google Inc. (Apple)", webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)",
         locale="zh-CN", timezone="Asia/Shanghai", hardware_concurrency=10, device_memory=16),
    # Mac with Intel GPU
    dict(ua=_MAC_UA_123, width=2560, height=1600, platform="MacIntel",
         webgl_vendor="Google Inc. (Intel Inc.)", webgl_renderer="ANGLE (Intel Inc., Intel(R) UHD Graphics 630 OpenGL Engine, OpenGL 4.1)",
         locale="zh-CN", timezone="Asia/Shanghai", hardware_concurrency=8, device_memory=16),
    # Linux 1080p
    dict(ua=_LNX_UA_124, width=1920, height=1080, platform="Linux x86_64",
         webgl_vendor="Google Inc. (NVIDIA Corporation)", webgl_renderer="ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1060/PCIe/SSE2, OpenGL 4.6.0)",
         locale="en-US", timezone="UTC", hardware_concurrency=8, device_memory=8),
    # Linux 1440p
    dict(ua=_LNX_UA_124, width=2560, height=1440, platform="Linux x86_64",
         webgl_vendor="Google Inc. (Mesa)", webgl_renderer="ANGLE (Mesa, Mesa Intel(R) UHD Graphics 620 (WHL GT2), OpenGL 4.6 (Core Profile) Mesa 23.0.4)",
         locale="en-US", timezone="UTC", hardware_concurrency=16, device_memory=16),
    # Windows en-US locale
    dict(ua=_WIN_UA_124, width=1920, height=1080, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         locale="en-US", timezone="America/New_York", hardware_concurrency=12, device_memory=16),
    # Windows en-US 1440p
    dict(ua=_WIN_UA_123, width=2560, height=1440, platform="Win32",
         webgl_vendor="Google Inc. (NVIDIA)", webgl_renderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         locale="en-US", timezone="America/Los_Angeles", hardware_concurrency=16, device_memory=32),
    # Windows en-GB
    dict(ua=_WIN_UA_124, width=1920, height=1080, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
         locale="en-GB", timezone="Europe/London", hardware_concurrency=16, device_memory=16),
    # Mac en-US
    dict(ua=_MAC_UA_124, width=1440, height=900, platform="MacIntel",
         webgl_vendor="Google Inc. (Apple)", webgl_renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
         locale="en-US", timezone="America/Chicago", hardware_concurrency=8, device_memory=16),
    # Windows 768 office laptop
    dict(ua=_WIN_UA_122, width=1280, height=768, platform="Win32",
         webgl_vendor="Google Inc. (Intel)", webgl_renderer="ANGLE (Intel, Intel(R) HD Graphics 4600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
         hardware_concurrency=4, device_memory=4),
    # Mac zh-TW
    dict(ua=_MAC_UA_124, width=1920, height=1080, platform="MacIntel",
         webgl_vendor="Google Inc. (Intel Inc.)", webgl_renderer="ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics 655 OpenGL Engine, OpenGL 4.1)",
         locale="zh-TW", timezone="Asia/Taipei", hardware_concurrency=4, device_memory=8),
]


def _build_pool() -> list[_ProfileEntry]:
    entries: list[_ProfileEntry] = []
    for i, defn in enumerate(_POOL_DEFINITIONS):
        profile = _make_profile(**defn)

        # Validate and auto-repair device coherence before adding to pool.
        # Read vendor/renderer from the definition dict (WebGLSimulation stores
        # them as extra kwargs which Pydantic doesn't expose as direct attributes).
        platform = defn.get("platform", "")
        vendor = defn.get("webgl_vendor", "")
        renderer = defn.get("webgl_renderer", "")
        ua = profile.user_agent or ""
        if vendor and renderer:
            violations = validate_profile_coherence(platform, vendor, renderer, ua)
            if violations:
                repaired = auto_repair_renderer(platform, vendor, renderer)
                if repaired != renderer:
                    # Rebuild the WebGLSimulation with the corrected renderer
                    profile.environment_simulation.webgl = WebGLSimulation(  # type: ignore[call-arg]
                        unmasked_vendor=vendor,
                        unmasked_renderer=repaired,
                    )

        snapshot_id = f"snap_{i:02d}"
        entries.append(_ProfileEntry(snapshot_id=snapshot_id, profile=profile))
    return entries


class BrowserProfilePool:
    """Maintains N diverse BrowserProfile snapshots and selects the least-recently-used
    one for a given domain, preventing fingerprint cohort tracking.

    Usage::

        pool = BrowserProfilePool()
        profile = pool.select("shopee.com.my")
        # ... use profile for crawl ...
        pool.record_usage("shopee.com.my", profile_hash, outcome="success")
    """

    def __init__(self, exclude_recent_hours: int = 1) -> None:
        self._pool = _build_pool()
        self._exclude_recent_hours = exclude_recent_hours

    def select(self, domain: str, exclude_recent_hours: int | None = None) -> BrowserProfile:
        """Select the best (least-recently-used, healthiest) profile for *domain*."""
        window = exclude_recent_hours if exclude_recent_hours is not None else self._exclude_recent_hours
        cutoff = time.time() - window * 3600
        domain_key = self._normalize_domain(domain)

        # Filter out profiles used recently for this domain
        candidates = [
            entry for entry in self._pool
            if entry.last_used_by.get(domain_key, 0) < cutoff
        ]
        if not candidates:
            # All profiles recently used — pick oldest usage
            candidates = sorted(self._pool, key=lambda e: e.last_used_by.get(domain_key, 0))

        # Sort by: highest health score, then least recently used globally
        candidates.sort(key=lambda e: (-e.health_score, e.last_used_by.get(domain_key, 0)))
        chosen = candidates[0]
        chosen.last_used_by[domain_key] = time.time()
        chosen.use_count += 1
        return chosen.profile

    def record_usage(self, domain: str, snapshot_id: str | None, outcome: str) -> None:
        """Record outcome for a profile snapshot (for future health scoring)."""
        domain_key = self._normalize_domain(domain)
        for entry in self._pool:
            if snapshot_id and entry.snapshot_id == snapshot_id:
                if outcome == "success":
                    entry.success_count += 1
                else:
                    entry.fail_count += 1
                entry.last_used_by[domain_key] = time.time()
                break

    def get_snapshot_id(self, profile: BrowserProfile) -> str | None:
        """Find the snapshot_id for a given profile object (identity check)."""
        for entry in self._pool:
            if entry.profile is profile:
                return entry.snapshot_id
        return None

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        parts = domain.strip().lower().split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return domain

    @property
    def pool_size(self) -> int:
        return len(self._pool)
