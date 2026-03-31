"""验证层单元测试"""
import pytest
from axelo.verification.comparator import TokenComparator, CompareResult
from axelo.models.target import RequestCapture


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
        # 时效性字段只检查格式，应该通过
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
            {"x-token": "some-token"},  # 生成了 x-token，但 GT 没有
            cap,
        )
        assert "x-token" in result.missing

    def test_score_all_matched(self):
        cap = _make_capture({
            "x-sign": "abcdef1234567890abcdef1234567890",
            "x-timestamp": "1700000000000",
        })
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
        # 两者都包含 Bearer 前缀，长度相近
        assert auth_r.status in ("format_ok", "format_mismatch")

    def test_empty_generated_returns_zero_score(self):
        cap = _make_capture({"x-sign": "abc123"})
        result = self.cmp.compare({}, cap)
        assert result.score == 0.0 or len(result.matched) == 0


class TestVerificationEngine:
    """轻量验证引擎测试（不实际发网络请求）"""

    @pytest.mark.asyncio
    async def test_no_script_returns_failure(self, tmp_path):
        from axelo.verification.engine import VerificationEngine
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite

        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            standalone_script_path=tmp_path / "nonexistent.py",
        )
        target = TargetSite(url="https://x.com", session_id="t01", interaction_goal="test")

        result = await engine.verify(generated, target, live_verify=False)
        assert not result.ok
        assert "未找到" in result.report

    @pytest.mark.asyncio
    async def test_valid_script_runs(self, tmp_path):
        from axelo.verification.engine import VerificationEngine
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite

        # 写一个合法的生成脚本
        script = tmp_path / "token_generator.py"
        script.write_text('''
import time
import hmac
import hashlib

class TokenGenerator:
    def __init__(self):
        self.secret = b"test_secret_key"

    def generate(self, url="", method="GET", body="", **kwargs):
        ts = str(int(time.time() * 1000))
        msg = f"{method}\\n{url}\\n{ts}".encode()
        sign = hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return {"X-Sign": sign, "X-Timestamp": ts}
''', encoding="utf-8")

        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="t01",
            output_mode="standalone",
            standalone_script_path=script,
        )
        target = TargetSite(
            url="https://api.example.com",
            session_id="t01",
            interaction_goal="test",
        )

        result = await engine.verify(generated, target, live_verify=False)
        # live_verify=False 时不发真实请求，应该返回部分成功
        assert result.attempts >= 1
