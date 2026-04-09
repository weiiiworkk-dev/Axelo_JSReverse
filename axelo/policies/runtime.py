from __future__ import annotations

from dataclasses import dataclass

from axelo.domain.services.blueTeam_detector import BlueteamCapabilityProfile
from axelo.config import settings
from axelo.models.execution import ExecutionTier
from axelo.models.target import BrowserProfile, TargetSite


@dataclass(frozen=True)
class RuntimePolicy:
    antibot_type: str
    crawl_rate: str
    requires_login: bool | None
    known_endpoint: str
    output_format: str
    request_interval_seconds: float
    post_navigation_wait_ms: int
    goto_wait_until: str
    requires_persistent_session: bool
    enable_trace_capture: bool
    max_runtime_retries: int

    def apply_to_profile(self, profile: BrowserProfile) -> BrowserProfile:
        return profile.model_copy(deep=True)

    def as_dict(self) -> dict:
        return {
            "antibot_type": self.antibot_type,
            "crawl_rate": self.crawl_rate,
            "requires_login": self.requires_login,
            "known_endpoint": self.known_endpoint,
            "output_format": self.output_format,
            "request_interval_seconds": self.request_interval_seconds,
            "post_navigation_wait_ms": self.post_navigation_wait_ms,
            "goto_wait_until": self.goto_wait_until,
            "requires_persistent_session": self.requires_persistent_session,
            "enable_trace_capture": self.enable_trace_capture,
            "max_runtime_retries": self.max_runtime_retries,
        }


def resolve_runtime_policy(target: TargetSite) -> RuntimePolicy:
    rate = target.crawl_rate
    request_interval = 1.0
    # === 使用增强的等待配置 ===
    post_wait_ms = settings.crawl_default_wait_ms  # 默认10秒
    # === 结束增强配置 ===
    if rate == "conservative":
        request_interval = 3.0
        post_wait_ms = max(post_wait_ms, 5000)  # 保守模式增加等待时间
    elif rate == "aggressive":
        request_interval = 0.0
        post_wait_ms = 800

    antibot = target.antibot_type
    # "networkidle" waits for zero in-flight requests for 500 ms — modern dynamic
    # sites (Amazon, etc.) never reach that state and time out.  Default to "load"
    # which fires as soon as the initial page load finishes.
    goto_wait_until = "load"
    max_runtime_retries = 1
    if antibot in {"cloudflare", "datadome", "akamai"}:
        post_wait_ms = max(post_wait_ms, 3000)
        max_runtime_retries = 2
    elif antibot == "custom":
        goto_wait_until = "domcontentloaded"

    requires_persistent_session = bool(target.requires_login or target.session_state.storage_state_path)
    if target.requires_login is True:
        post_wait_ms = max(post_wait_ms, 2500)
        max_runtime_retries = max(max_runtime_retries, 2)

    if target.known_endpoint:
        post_wait_ms = max(1000, post_wait_ms - 500)
    if target.known_endpoint and target.target_hint and target.requires_login is False:
        post_wait_ms = min(post_wait_ms, 700)
        max_runtime_retries = 1

    plan = target.execution_plan
    if plan:
        if plan.tier == ExecutionTier.BROWSER_LIGHT:
            goto_wait_until = "domcontentloaded" if target.known_endpoint else "load"
            post_wait_ms = min(post_wait_ms, 1200)
            max_runtime_retries = min(max_runtime_retries, plan.max_crawl_retries)
        elif plan.tier == ExecutionTier.ADAPTER_REUSE:
            post_wait_ms = 0
            max_runtime_retries = 1
        elif plan.tier == ExecutionTier.MANUAL_REVIEW:
            post_wait_ms = 0
            max_runtime_retries = 1

        requires_persistent_session = requires_persistent_session or plan.tier == ExecutionTier.BROWSER_FULL
        enable_trace_capture = plan.enable_trace_capture
        max_runtime_retries = max(1, min(max_runtime_retries, plan.max_crawl_retries))
    else:
        enable_trace_capture = True

    # Apply adaptive adjustments based on detected blue team capabilities.
    blueteam_profile: BlueteamCapabilityProfile | None = getattr(target, "blueteam_profile", None)
    if blueteam_profile is not None:
        if blueteam_profile.uses_tls_fingerprinting:
            # Back off faster when TLS fingerprinting is active — retrying the same
            # fingerprint will always fail.  Reduce retries to avoid burning budget.
            max_runtime_retries = min(max_runtime_retries, 1)
        if blueteam_profile.uses_behavioral_ml:
            # ML systems score request cadence — slow down significantly.
            request_interval = max(request_interval, 4.0)
            post_wait_ms = max(post_wait_ms, 4000)
        if blueteam_profile.uses_dom_challenge:
            # DOM challenges need headful resolution time.
            post_wait_ms = max(post_wait_ms, 3000)
            max_runtime_retries = max(max_runtime_retries, 2)

    return RuntimePolicy(
        antibot_type=antibot,
        crawl_rate=rate,
        requires_login=target.requires_login,
        known_endpoint=target.known_endpoint,
        output_format=target.output_format,
        request_interval_seconds=request_interval,
        post_navigation_wait_ms=post_wait_ms,
        goto_wait_until=goto_wait_until,
        requires_persistent_session=requires_persistent_session,
        enable_trace_capture=enable_trace_capture,
        max_runtime_retries=max_runtime_retries,
    )
