from __future__ import annotations

from dataclasses import dataclass

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
    force_stealth: bool

    def apply_to_profile(self, profile: BrowserProfile) -> BrowserProfile:
        profile.stealth = profile.stealth or self.force_stealth
        return profile

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
            "force_stealth": self.force_stealth,
        }


def resolve_runtime_policy(target: TargetSite) -> RuntimePolicy:
    rate = target.crawl_rate
    request_interval = 1.0
    post_wait_ms = 2000
    if rate == "conservative":
        request_interval = 3.0
        post_wait_ms = 3500
    elif rate == "aggressive":
        request_interval = 0.0
        post_wait_ms = 800

    antibot = target.antibot_type
    goto_wait_until = "networkidle"
    force_stealth = False
    if antibot in {"cloudflare", "datadome", "akamai"}:
        # Strict anti-bot sites are usually sensitive to bot signals.
        force_stealth = True
        goto_wait_until = "load"
        post_wait_ms = max(post_wait_ms, 3000)
    elif antibot == "custom":
        goto_wait_until = "domcontentloaded"

    if target.requires_login is True:
        force_stealth = True
        post_wait_ms = max(post_wait_ms, 2500)

    if target.known_endpoint:
        post_wait_ms = max(1000, post_wait_ms - 500)

    return RuntimePolicy(
        antibot_type=antibot,
        crawl_rate=rate,
        requires_login=target.requires_login,
        known_endpoint=target.known_endpoint,
        output_format=target.output_format,
        request_interval_seconds=request_interval,
        post_navigation_wait_ms=post_wait_ms,
        goto_wait_until=goto_wait_until,
        force_stealth=force_stealth,
    )

