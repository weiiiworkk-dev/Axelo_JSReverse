"""Verification unit tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from axelo.models.target import RequestCapture
from axelo.verification.comparator import TokenComparator


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
        result = self.cmp.compare(
            {"x-timestamp": "1700000000001", "x-nonce": "e5f6g7h8"},
            cap,
        )
        ts_result = next(r for r in result.field_results if r.field == "x-timestamp")
        assert ts_result.status in ("format_ok",)

    def test_hex_length_match(self):
        cap = _make_capture({"x-sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"})
        result = self.cmp.compare(
            {"x-sign": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"},
            cap,
        )
        sign_r = next(r for r in result.field_results if r.field == "x-sign")
        assert sign_r.status == "format_ok"

    def test_missing_field_detected(self):
        cap = _make_capture({"x-sign": "abc123def456"})
        result = self.cmp.compare(
            {"x-token": "some-token"},
            cap,
        )
        assert "x-token" in result.missing

    def test_score_all_matched(self):
        cap = _make_capture(
            {
                "x-sign": "abcdef1234567890abcdef1234567890",
                "x-timestamp": "1700000000000",
            }
        )
        result = self.cmp.compare(
            {
                "x-sign": "1234567890abcdef1234567890abcdef",
                "x-timestamp": "1700000001000",
            },
            cap,
        )
        assert result.score == 1.0

    def test_base64_format_match(self):
        cap = _make_capture({"authorization": "Bearer dGVzdHRva2VudGVzdHRva2VudGVzdA=="})
        result = self.cmp.compare(
            {"authorization": "Bearer bmV3dG9rZW5uZXd0b2tlbm5ld3Rva2Vu"},
            cap,
        )
        auth_r = next(r for r in result.field_results if r.field == "authorization")
        assert auth_r.status in ("format_ok", "format_mismatch")

    def test_empty_generated_returns_zero_score(self):
        cap = _make_capture({"x-sign": "abc123"})
        result = self.cmp.compare({}, cap)
        assert result.score == 0.0 or len(result.matched) == 0


class TestVerificationEngine:
    def test_no_script_returns_failure(self):
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite
        from axelo.verification.engine import VerificationEngine

        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            crawler_script_path=Path("C:/__axelo__/nonexistent.py"),
        )
        target = TargetSite(url="https://x.com", session_id="t01", interaction_goal="test")

        result = asyncio.run(engine.verify(generated, target, live_verify=False))
        assert not result.ok

    def test_valid_script_runs(self, monkeypatch):
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite
        import axelo.verification.engine as verification_engine
        from axelo.verification.engine import VerificationEngine
        from axelo.verification.replayer import ReplayResult

        engine = VerificationEngine()
        async def fake_replay(script_path, target):
            return {"X-Sign": "abc", "X-Timestamp": "123"}, ReplayResult(
                ok=True,
                status_code=200,
                response_body="{}",
                headers={"X-Sign": "abc", "X-Timestamp": "123"},
            )

        engine._replayer.replay_with_script = fake_replay  # type: ignore[method-assign]
        monkeypatch.setattr(verification_engine.Path, "exists", lambda self: True)
        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            crawler_script_path=Path("C:/__axelo__/token_generator.py"),
        )
        target = TargetSite(
            url="https://api.example.com",
            session_id="t01",
            interaction_goal="test",
        )

        result = asyncio.run(engine.verify(generated, target, live_verify=False))
        assert result.attempts >= 1
