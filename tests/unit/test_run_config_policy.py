from __future__ import annotations

import pytest
from pydantic import ValidationError

from axelo.models.run_config import RunConfig
from axelo.models.target import TargetSite
from axelo.policies import resolve_runtime_policy


def test_run_config_valid():
    cfg = RunConfig(
        url="https://example.com",
        goal="reverse signature",
        target_hint="iphone 15",
        use_case="partner",
        authorization_status="authorized",
        replay_mode="authorized_replay",
        mode_name="interactive",
        budget_usd=3.0,
        known_endpoint="/api/search",
        antibot_type="cloudflare",
        requires_login=True,
        output_format="json_file",
        crawl_rate="conservative",
        crawl_item_limit=300,
        crawl_page_limit=12,
    )
    kwargs = cfg.runtime_kwargs()
    assert kwargs["target_hint"] == "iphone 15"
    assert kwargs["use_case"] == "partner"
    assert kwargs["authorization_status"] == "authorized"
    assert kwargs["replay_mode"] == "authorized_replay"
    assert kwargs["known_endpoint"] == "/api/search"
    assert kwargs["antibot_type"] == "cloudflare"
    assert kwargs["requires_login"] is True
    assert kwargs["output_format"] == "json_file"
    assert kwargs["crawl_rate"] == "conservative"
    assert kwargs["crawl_item_limit"] == 300
    assert kwargs["crawl_page_limit"] == 12


def test_run_config_invalid_url():
    with pytest.raises(ValidationError):
        RunConfig(
            url="example.com",
            goal="x",
        )


def test_runtime_policy_cloudflare_conservative():
    target = TargetSite(
        url="https://example.com",
        session_id="t01",
        interaction_goal="demo",
        antibot_type="cloudflare",
        crawl_rate="conservative",
        requires_login=True,
        known_endpoint="/api/x",
    )
    policy = resolve_runtime_policy(target)
    assert policy.goto_wait_until == "load"
    assert policy.request_interval_seconds == 3.0
    assert policy.post_navigation_wait_ms >= 3000
    profile = policy.apply_to_profile(target.browser_profile)
    assert profile is not target.browser_profile
    assert profile.environment_simulation.profile_name == "desktop"


def test_run_config_rejects_invalid_crawl_limits():
    with pytest.raises(ValidationError):
        RunConfig(
            url="https://example.com",
            goal="reverse signature",
            crawl_item_limit=0,
        )

    with pytest.raises(ValidationError):
        RunConfig(
            url="https://example.com",
            goal="reverse signature",
            crawl_page_limit=0,
        )
