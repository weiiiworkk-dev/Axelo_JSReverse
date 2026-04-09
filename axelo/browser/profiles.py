from __future__ import annotations

import random
from axelo.models.target import (
    BatterySimulation,
    BrowserProfile,
    EnvironmentSimulation,
    InteractionSimulation,
    MediaSimulation,
    PointerPathSimulation,
)


def _random_seed() -> int:
    """Generate random seed for mouse movement"""
    return random.randint(1000, 9999)


PROFILES: dict[str, BrowserProfile] = {
    "default": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport_width=1920,
        viewport_height=1080,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        environment_simulation=EnvironmentSimulation(
            profile_name="desktop",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=1.0,
            has_touch=False,
            is_mobile=False,
            battery=BatterySimulation(charging=True, level=1.0),
            media=MediaSimulation(
                pointer="fine",
                hover="hover",
                any_pointer="fine",
                any_hover="hover",
                hardware_concurrency=8,
                device_memory=8,
                max_touch_points=0,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="synthetic_performance",
            mode="playwright_mouse",
            high_frequency_dispatch=False,
            pointer=PointerPathSimulation(
                default_seed=1337,
                sample_rate_hz=60,
                duration_ms=1200,
                jitter_px=1.25,
                curvature=0.18,
                hover_pause_ms=0,
            ),
        ),
    ),
    # ==========================================================================
    # NEW PROFILES - Anti-detection enhanced
    # ==========================================================================
    "chrome_windows_11": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 "
            "Edg/131.0.0.0"
        ),
        viewport_width=1920,
        viewport_height=1080,
        locale="en-US",
        timezone="America/New_York",
        environment_simulation=EnvironmentSimulation(
            profile_name="chrome_windows_11",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=1.0,
            has_touch=False,
            is_mobile=False,
            battery=BatterySimulation(charging=True, level=0.85),
            media=MediaSimulation(
                pointer="fine",
                hover="hover",
                any_pointer="fine",
                any_hover="hover",
                hardware_concurrency=16,
                device_memory=16,
                max_touch_points=0,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="human_like",
            mode="dispatch",
            high_frequency_dispatch=True,
            pointer=PointerPathSimulation(
                default_seed=_random_seed(),
                sample_rate_hz=60,
                duration_ms=1500,
                jitter_px=2.0,
                curvature=0.25,
                hover_pause_ms=150,
            ),
        ),
    ),
    "edge_windows_10": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36 "
            "Edg/130.0.0.0"
        ),
        viewport_width=1366,
        viewport_height=768,
        locale="en-GB",
        timezone="Europe/London",
        environment_simulation=EnvironmentSimulation(
            profile_name="edge_windows_10",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=1.0,
            has_touch=False,
            is_mobile=False,
            battery=BatterySimulation(charging=True, level=0.9),
            media=MediaSimulation(
                pointer="fine",
                hover="hover",
                any_pointer="fine",
                any_hover="hover",
                hardware_concurrency=8,
                device_memory=8,
                max_touch_points=0,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="human_like",
            mode="dispatch",
            high_frequency_dispatch=True,
            pointer=PointerPathSimulation(
                default_seed=_random_seed(),
                sample_rate_hz=60,
                duration_ms=1800,
                jitter_px=1.8,
                curvature=0.2,
                hover_pause_ms=200,
            ),
        ),
    ),
    "safari_macos": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Safari/605.1.15"
        ),
        viewport_width=1440,
        viewport_height=900,
        locale="en-US",
        timezone="America/Los_Angeles",
        environment_simulation=EnvironmentSimulation(
            profile_name="safari_macos",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=2.0,
            has_touch=False,
            is_mobile=False,
            battery=BatterySimulation(charging=True, level=0.75),
            media=MediaSimulation(
                pointer="fine",
                hover="hover",
                any_pointer="fine",
                any_hover="hover",
                hardware_concurrency=8,
                device_memory=8,
                max_touch_points=0,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="human_like",
            mode="dispatch",
            high_frequency_dispatch=True,
            pointer=PointerPathSimulation(
                default_seed=_random_seed(),
                sample_rate_hz=60,
                duration_ms=1600,
                jitter_px=2.2,
                curvature=0.22,
                hover_pause_ms=180,
            ),
        ),
    ),
    "firefox_windows": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
            "Gecko/20100101 Firefox/132.0"
        ),
        viewport_width=1920,
        viewport_height=1080,
        locale="de-DE",
        timezone="Europe/Berlin",
        environment_simulation=EnvironmentSimulation(
            profile_name="firefox_windows",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=1.0,
            has_touch=False,
            is_mobile=False,
            battery=BatterySimulation(charging=False, level=0.6),
            media=MediaSimulation(
                pointer="fine",
                hover="hover",
                any_pointer="fine",
                any_hover="hover",
                hardware_concurrency=12,
                device_memory=16,
                max_touch_points=0,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="human_like",
            mode="dispatch",
            high_frequency_dispatch=True,
            pointer=PointerPathSimulation(
                default_seed=_random_seed(),
                sample_rate_hz=60,
                duration_ms=1400,
                jitter_px=1.5,
                curvature=0.18,
                hover_pause_ms=120,
            ),
        ),
    ),
    "mobile": BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        viewport_width=390,
        viewport_height=844,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        environment_simulation=EnvironmentSimulation(
            profile_name="mobile",
            color_scheme="light",
            reduced_motion="no-preference",
            device_scale_factor=3.0,
            has_touch=True,
            is_mobile=True,
            battery=BatterySimulation(charging=True, level=0.82),
            media=MediaSimulation(
                pointer="coarse",
                hover="none",
                any_pointer="coarse",
                any_hover="none",
                hardware_concurrency=6,
                device_memory=4,
                max_touch_points=5,
            ),
        ),
        interaction_simulation=InteractionSimulation(
            profile_name="synthetic_performance",
            mode="playwright_mouse",
            high_frequency_dispatch=False,
            pointer=PointerPathSimulation(
                default_seed=2048,
                sample_rate_hz=75,
                duration_ms=1400,
                jitter_px=1.5,
                curvature=0.22,
                hover_pause_ms=20,
            ),
        ),
    ),
}


def get_random_profile() -> BrowserProfile:
    """Get a random profile for anti-detection"""
    # Exclude 'mobile' and 'default' - use other profiles
    available = [p for p in PROFILES.keys() if p not in ["mobile", "default"]]
    name = random.choice(available)
    return PROFILES[name]


def get_stealth_profile() -> BrowserProfile:
    """Get a stealth-optimized profile"""
    stealth_profiles = ["chrome_windows_11", "edge_windows_10", "safari_macos"]
    name = random.choice(stealth_profiles)
    return PROFILES[name]
