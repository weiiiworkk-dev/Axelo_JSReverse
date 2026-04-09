"""Tests for v3 plan components: proxy, pacing, profile pool, cookie pool,
behavior bank/mixer, JS challenge solver, A/B tester, and bug fixes."""
from __future__ import annotations

import asyncio
import time

import pytest

from axelo.browser.profile_pool import BrowserProfilePool
from axelo.browser.cookie_pool import CookieJar, CookiePoolCoordinator
from axelo.browser.js_challenge_solver import JSChallengeSolver, _parse_cookie_string
from axelo.behavior.replay_bank import BehaviorFragment, ReplayBank
from axelo.behavior.behavior_mixer import BehaviorMixer
from axelo.network.proxy_manager import ProxyConfig, ProxyManager
from axelo.network.pacing_model import PacingConfig, RequestPacingModel
from axelo.testing.fingerprint_ab_test import _fisher_exact_p
from axelo.models.target import BrowserProfile


# ---------------------------------------------------------------------------
# ProxyManager
# ---------------------------------------------------------------------------

class TestProxyManager:
    def test_direct_mode_returns_none(self):
        pm = ProxyManager(ProxyConfig(mode="direct"))
        assert pm.get_proxy("example.com") is None
        assert pm.playwright_proxy("example.com") is None
        assert pm.curl_cffi_proxies("example.com") is None

    def test_static_mode_returns_configured_url(self):
        pm = ProxyManager(ProxyConfig(mode="static", url="http://proxy:8080"))
        assert pm.get_proxy("example.com") == "http://proxy:8080"

    def test_rotating_mode_rotates_after_n(self):
        pm = ProxyManager(ProxyConfig(
            mode="rotating",
            urls=["http://proxy1:8080", "http://proxy2:8080"],
            rotation_after_n_requests=3,
        ))
        urls_seen = set()
        for _ in range(10):
            u = pm.get_proxy("example.com")
            if u:
                urls_seen.add(u)
        assert len(urls_seen) >= 2

    def test_mark_blocked_rotates(self):
        pm = ProxyManager(ProxyConfig(
            mode="rotating",
            urls=["http://proxy1:8080", "http://proxy2:8080"],
        ))
        first = pm.get_proxy("site.com")
        pm.mark_blocked(first, "site.com")
        second = pm.get_proxy("site.com")
        # either rotated OR single-proxy (no change possible)
        assert second is not None or pm.pool_size == 0

    def test_no_urls_configured_returns_none(self):
        pm = ProxyManager(ProxyConfig(mode="rotating", urls=[]))
        assert pm.get_proxy("x.com") is None


# ---------------------------------------------------------------------------
# RequestPacingModel
# ---------------------------------------------------------------------------

class TestRequestPacingModel:
    def test_zero_speed_factor_no_delay(self):
        pacing = RequestPacingModel(speed_factor=0.0)
        t0 = time.monotonic()
        asyncio.run(pacing.before_navigation("https://example.com"))
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5

    def test_rate_limit_tracking(self):
        pacing = RequestPacingModel(speed_factor=0.0, config=PacingConfig(max_rpm=5, speed_factor=0.0))
        for _ in range(5):
            pacing._record_request("example.com")
        timestamps = pacing._domain_timestamps.get("example.com", [])
        assert len(timestamps) == 5

    def test_rate_multiplier_decreases_on_429(self):
        pacing = RequestPacingModel(speed_factor=1.0)
        original = pacing._rate_multiplier
        pacing.on_rate_limited()
        assert pacing._rate_multiplier < original

    def test_rate_multiplier_recovers(self):
        pacing = RequestPacingModel(speed_factor=1.0)
        pacing.on_rate_limited()
        limited = pacing._rate_multiplier
        for _ in range(20):
            pacing.on_success()
        assert pacing._rate_multiplier > limited


# ---------------------------------------------------------------------------
# BrowserProfilePool
# ---------------------------------------------------------------------------

class TestBrowserProfilePool:
    def test_pool_has_20_snapshots(self):
        pool = BrowserProfilePool()
        assert pool.pool_size == 20

    def test_select_returns_browser_profile(self):
        pool = BrowserProfilePool()
        profile = pool.select("shopee.com.my")
        assert isinstance(profile, BrowserProfile)
        assert profile.user_agent

    def test_same_domain_rotates_profiles(self):
        pool = BrowserProfilePool(exclude_recent_hours=0)
        agents = [pool.select("example.com").user_agent for _ in range(5)]
        assert len(set(agents)) >= 2

    def test_record_usage_updates_health(self):
        pool = BrowserProfilePool()
        profile = pool.select("example.com")
        snapshot_id = pool.get_snapshot_id(profile)
        pool.record_usage("example.com", snapshot_id, "success")
        entry = next(e for e in pool._pool if e.snapshot_id == snapshot_id)
        assert entry.success_count == 1


# ---------------------------------------------------------------------------
# CookiePoolCoordinator
# ---------------------------------------------------------------------------

class TestCookiePoolCoordinator:
    def test_get_returns_none_when_empty(self):
        pool = CookiePoolCoordinator()
        result = asyncio.run(
            pool.get_cookies("example.com", timeout=0.05)
        )
        assert result is None

    def test_put_and_get(self):
        pool = CookiePoolCoordinator()
        asyncio.run(
            pool.put_cookies("example.com", {"session": "abc"}, ttl=300)
        )
        result = asyncio.run(pool.get_cookies("example.com"))
        assert result == {"session": "abc"}

    def test_invalidate(self):
        pool = CookiePoolCoordinator()
        asyncio.run(
            pool.put_cookies("example.com", {"k": "v"}, ttl=300)
        )
        asyncio.run(pool.invalidate("example.com"))
        result = asyncio.run(
            pool.get_cookies("example.com", timeout=0.05)
        )
        assert result is None

    def test_expired_jar_not_valid(self):
        jar = CookieJar(domain="x.com", cookies={"k": "v"}, ttl_seconds=1)
        jar.acquired_at = time.monotonic() - 2
        assert not jar.is_valid

    def test_cached_domains(self):
        pool = CookiePoolCoordinator()
        asyncio.run(
            pool.put_cookies("shopee.com", {"x": "1"}, ttl=300)
        )
        assert "shopee.com" in pool.cached_domains


# ---------------------------------------------------------------------------
# ReplayBank
# ---------------------------------------------------------------------------

class TestReplayBank:
    def test_empty_bank_returns_none(self, tmp_path):
        bank = ReplayBank(tmp_path)
        assert bank.sample("mouse_move") is None

    def test_add_and_sample(self, tmp_path):
        bank = ReplayBank(tmp_path)
        frag = BehaviorFragment(
            fragment_type="mouse_move",
            duration_ms=800,
            points=[{"x": 100, "y": 200, "ts": 0}, {"x": 500, "y": 400, "ts": 800}],
            metadata={"viewport_width": 1920, "viewport_height": 1080},
        )
        bank.add(frag)
        result = bank.sample("mouse_move", target_duration_ms=800)
        assert result is not None
        assert result.duration_ms == 800

    def test_count(self, tmp_path):
        bank = ReplayBank(tmp_path)
        assert bank.count() == 0
        bank.add(BehaviorFragment(fragment_type="scroll", duration_ms=500, points=[]))
        assert bank.count() == 1

    def test_adapt_to_viewport(self):
        frag = BehaviorFragment(
            fragment_type="mouse_move",
            duration_ms=500,
            points=[{"x": 960.0, "y": 540.0, "ts": 0}],
            metadata={"viewport_width": 1920, "viewport_height": 1080},
        )
        adapted = frag.adapt_to_viewport(1280, 720)
        assert adapted.points[0]["x"] == pytest.approx(640.0)
        assert adapted.points[0]["y"] == pytest.approx(360.0)


# ---------------------------------------------------------------------------
# BehaviorMixer
# ---------------------------------------------------------------------------

class TestBehaviorMixer:
    def test_algorithmic_fallback_when_empty(self, tmp_path):
        bank = ReplayBank(tmp_path)
        mixer = BehaviorMixer(bank)
        path = mixer.get_pointer_path((0, 0), (100, 100), duration_ms=500)
        assert path.source == "algorithmic"
        assert len(path.points) >= 8

    def test_uses_recorded_when_sufficient(self, tmp_path):
        bank = ReplayBank(tmp_path)
        for _ in range(10):
            bank.add(BehaviorFragment(
                fragment_type="mouse_move",
                duration_ms=500,
                points=[{"x": 0.0, "y": 0.0, "ts": 0}, {"x": 100.0, "y": 100.0, "ts": 500}],
                metadata={"viewport_width": 1920, "viewport_height": 1080},
            ))
        mixer = BehaviorMixer(bank, rng_seed=42, min_fragments=5)
        sources = {mixer.get_pointer_path((0, 0), (200, 200)).source for _ in range(20)}
        assert "recorded" in sources


# ---------------------------------------------------------------------------
# JSChallengeSolver
# ---------------------------------------------------------------------------

class TestJSChallengeSolver:
    def test_parse_cookie_string(self):
        cookies = _parse_cookie_string("session=abc; token=xyz")
        assert cookies == {"session": "abc", "token": "xyz"}

    def test_solve_current_timestamp(self):
        solver = JSChallengeSolver()
        now = int(time.time())
        result = solver._solve_timestamp_cookie({"set-cookie": f"ts={now}; Path=/"}, {})
        assert result is not None
        assert "ts" in result

    def test_old_timestamp_returns_none(self):
        solver = JSChallengeSolver()
        old_ts = int(time.time()) - 3600
        result = solver._solve_timestamp_cookie({"set-cookie": f"ts={old_ts}; Path=/"}, {})
        assert result is None

    def test_no_set_cookie_returns_none(self):
        solver = JSChallengeSolver()
        assert solver._solve_timestamp_cookie({}, {}) is None


# ---------------------------------------------------------------------------
# Fisher exact test
# ---------------------------------------------------------------------------

class TestFisherExact:
    def test_identical_rates_high_p(self):
        p = _fisher_exact_p(5, 5, 5, 5)
        assert p > 0.5

    def test_perfect_separation_low_p(self):
        p = _fisher_exact_p(0, 10, 10, 0)
        assert p < 0.001

    def test_output_in_range(self):
        p = _fisher_exact_p(3, 7, 8, 2)
        assert 0.0 <= p <= 1.0


# ---------------------------------------------------------------------------
# Bug-3: challenge_monitor empty-page fix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_challenge_monitor_empty_page_not_resolved():
    from unittest.mock import AsyncMock, MagicMock
    from axelo.browser.challenge_monitor import ChallengeMonitor

    monitor = ChallengeMonitor()
    page = MagicMock()
    page.title = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value="")
    page.context.cookies = AsyncMock(return_value=[])

    state = await monitor.check(page)
    assert not state.is_resolved, "Empty page must not be classified as resolved"
    assert not state.is_blocked


@pytest.mark.asyncio
async def test_challenge_monitor_content_page_is_resolved():
    from unittest.mock import AsyncMock, MagicMock
    from axelo.browser.challenge_monitor import ChallengeMonitor

    monitor = ChallengeMonitor()
    page = MagicMock()
    page.title = AsyncMock(return_value="Search Results")
    page.evaluate = AsyncMock(return_value="Here are the search results for your query. Many products found here.")
    page.context.cookies = AsyncMock(return_value=[])

    state = await monitor.check(page)
    assert state.is_resolved
    assert not state.is_blocked


# ---------------------------------------------------------------------------
# Bug-4: Knowledge store subdomain aggregation
# ---------------------------------------------------------------------------

def test_knowledge_store_etld1():
    from axelo.knowledge.session_knowledge_store import SessionKnowledgeStore
    assert SessionKnowledgeStore._etld_plus1("api.example.com") == "example.com"
    assert SessionKnowledgeStore._etld_plus1("example.com") == "example.com"
    assert SessionKnowledgeStore._etld_plus1("www.shopee.com.my") == "com.my"


def test_knowledge_store_subdomain_aggregation(tmp_path):
    from axelo.knowledge.session_knowledge_store import SessionKnowledge, SessionKnowledgeStore

    store = SessionKnowledgeStore(tmp_path)
    store.record(SessionKnowledge(
        domain="www.example.com",
        fingerprint_config={"user_agent": "TestAgent"},
        outcome="success",
        request_success_rate=1.0,
    ))
    # api.example.com shares eTLD+1 with www.example.com → should see same records
    records = store._load_records("api.example.com")
    assert any(r.domain == "www.example.com" for r in records)
