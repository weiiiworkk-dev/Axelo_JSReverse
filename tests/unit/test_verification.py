from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from axelo.config import settings
from axelo.models.codegen import GeneratedCode
from axelo.models.target import RequestCapture, TargetSite
from axelo.verification.comparator import TokenComparator
from axelo.verification.data_quality import evaluate_data_quality
from axelo.verification.engine import VerificationEngine, _detect_risk_control
from axelo.verification.replayer import ReplayResult, RequestReplayer
from axelo.verification.stability import evaluate_stability


def _make_capture(headers: dict) -> RequestCapture:
    return RequestCapture(
        url="https://api.example.com/data",
        method="POST",
        request_headers=headers,
        response_status=200,
    )


class TestTokenComparator:
    def setup_method(self):
        self.cmp = TokenComparator()

    def test_temporal_field_format_ok(self):
        cap = _make_capture({"x-timestamp": "1700000000000", "x-nonce": "a1b2c3d4"})
        result = self.cmp.compare({"x-timestamp": "1700000000001", "x-nonce": "e5f6g7h8"}, cap)
        ts_result = next(item for item in result.field_results if item.field == "x-timestamp")
        assert ts_result.status == "format_ok"

    def test_missing_field_detected(self):
        cap = _make_capture({"x-sign": "abc123def456"})
        result = self.cmp.compare({"x-token": "some-token"}, cap)
        assert "x-token" in result.missing


def test_data_quality_list_payload():
    result = evaluate_data_quality([{"id": 1, "name": "x"}])
    assert result.ok is True
    assert result.record_count == 1
    assert "id" in result.preview_keys


def test_stability_consistent_samples():
    result = evaluate_stability(
        [
            ({"X-Sign": "a", "X-Timestamp": "1"}, [{"id": 1}]),
            ({"X-Sign": "b", "X-Timestamp": "2"}, [{"id": 2}]),
        ]
    )
    assert result.ok is True
    assert result.consistent_header_keys is True
    assert result.consistent_output_shape is True


class TestVerificationEngine:
    def test_no_script_returns_failure(self):
        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            crawler_script_path=Path("C:/__axelo__/nonexistent.py"),
        )
        target = TargetSite(url="https://x.com", session_id="t01", interaction_goal="test")

        result = asyncio.run(engine.verify(generated, target, live_verify=False))
        assert result.ok is False

    def test_valid_script_runs(self, monkeypatch):
        engine = VerificationEngine()

        async def fake_replay(script_path, target):
            return {"X-Sign": "abc", "X-Timestamp": "123"}, ReplayResult(
                ok=True,
                status_code=200,
                response_body="{}",
                headers={"X-Sign": "abc", "X-Timestamp": "123"},
                generated_data=[{"id": 1}],
            )

        async def fake_stability(script_path, target, samples):
            return evaluate_stability(samples or [({"X-Sign": "abc"}, [{"id": 1}])])

        engine._replayer.replay_with_script = fake_replay  # type: ignore[method-assign]
        engine._stability_check = fake_stability  # type: ignore[method-assign]
        monkeypatch.setattr(Path, "exists", lambda self: True)

        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            crawler_script_path=Path("C:/__axelo__/token_generator.py"),
        )
        target = TargetSite(url="https://api.example.com", session_id="t01", interaction_goal="test")

        result = asyncio.run(engine.verify(generated, target, live_verify=False))
        assert result.attempts >= 1
        assert result.data_quality is not None
        assert result.stability is not None

    def test_risk_control_response_stops_retry(self, monkeypatch):
        engine = VerificationEngine()

        async def fake_replay(script_path, target):
            return {"Origin": "https://www.lazada.com.my"}, ReplayResult(
                ok=True,
                status_code=200,
                response_body='{"ret":["FAIL_SYS_USER_VALIDATE","RGV587_ERROR"],"data":{"url":"https://www.lazada.com.my/_____tmd_____/punish?x5secdata=abc"}}',
                headers={"Origin": "https://www.lazada.com.my"},
                generated_data={"ret": ["FAIL_SYS_USER_VALIDATE"]},
            )

        async def fake_stability(script_path, target, samples):
            return evaluate_stability(samples or [({"Origin": "x"}, [{"id": 1}])])

        engine._replayer.replay_with_script = fake_replay  # type: ignore[method-assign]
        engine._stability_check = fake_stability  # type: ignore[method-assign]
        monkeypatch.setattr(Path, "exists", lambda self: True)

        generated = GeneratedCode(
            session_id="t02",
            output_mode="standalone",
            crawler_script_path=Path("C:/__axelo__/token_generator.py"),
        )
        target = TargetSite(url="https://api.example.com", session_id="t02", interaction_goal="test")

        result = asyncio.run(engine.verify(generated, target, live_verify=False))
        assert result.ok is False
        assert result.risk_control_reason == "risk-control challenge page detected"
        assert "risk_control detected" in result.report


def test_detect_risk_control_from_challenge_response():
    replay = ReplayResult(
        ok=True,
        status_code=200,
        response_body='{"ret":["FAIL_SYS_USER_VALIDATE","RGV587_ERROR"],"data":{"url":"https://www.lazada.com.my/_____tmd_____/punish?x5secdata=abc"}}',
    )

    assert _detect_risk_control(replay) == "risk-control challenge page detected"


@pytest.mark.asyncio
async def test_replayer_executes_generated_code_in_isolated_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)
    script = tmp_path / "crawler.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "Path('owned.txt').write_text('child-only', encoding='utf-8')",
                "",
                "class GeneratedCrawler:",
                "    def __init__(self):",
                "        self._last_headers = {'X-Sign': 'ok'}",
                "",
                "    def crawl(self):",
                "        return {'ok': True}",
            ]
        ),
        encoding="utf-8",
    )

    replayer = RequestReplayer()
    target = TargetSite(url="https://example.com", session_id="iso01", interaction_goal="demo")
    result = await replayer.execute_crawl_subprocess(script, target, timeout=5.0)

    assert result.error is None
    assert result.headers == {"X-Sign": "ok"}
    assert result.crawl_data == {"ok": True}
    assert not (tmp_path / "owned.txt").exists()


@pytest.mark.asyncio
async def test_replayer_times_out_subprocess_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)
    script = tmp_path / "crawler.py"
    script.write_text(
        "\n".join(
            [
                "import time",
                "time.sleep(5)",
                "",
                "class SlowCrawler:",
                "    def crawl(self):",
                "        return {'ok': True}",
            ]
        ),
        encoding="utf-8",
    )

    replayer = RequestReplayer()
    target = TargetSite(url="https://example.com", session_id="iso02", interaction_goal="demo")
    result = await replayer.execute_crawl_subprocess(script, target, timeout=0.2)

    assert result.error is not None
    assert "timed out" in result.error
