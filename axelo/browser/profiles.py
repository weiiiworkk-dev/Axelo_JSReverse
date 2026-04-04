from __future__ import annotations

from axelo.models.target import (
    BatterySimulation,
    BrowserProfile,
    EnvironmentSimulation,
    InteractionSimulation,
    MediaSimulation,
    PointerPathSimulation,
)


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
