"""难度分类器单元测试"""
import pytest
from axelo.models.analysis import StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite, BrowserProfile
from axelo.classifier.rules import classify, DifficultyScore


def _make_target(url: str) -> TargetSite:
    return TargetSite(url=url, session_id="t01", interaction_goal="test")


def _make_static(crypto_imports: list[str], env_access: list[str]) -> dict:
    sa = StaticAnalysis(
        bundle_id="b01",
        crypto_imports=crypto_imports,
        env_access=env_access,
    )
    return {"b01": sa}


class TestClassifier:
    def test_easy_no_crypto(self):
        target = _make_target("https://simple.com")
        static = _make_static([], [])
        result = classify(target, static)
        assert result.level in ("easy", "medium")

    def test_medium_hmac(self):
        target = _make_target("https://shop.com")
        static = _make_static(["hmac", "sha256"], [])
        result = classify(target, static)
        assert result.level in ("medium", "hard")

    def test_hard_canvas_fingerprint(self):
        target = _make_target("https://secure.com")
        static = _make_static(["hmac"], ["canvas", "webgl"])
        result = classify(target, static)
        assert result.level in ("hard", "extreme")

    def test_extreme_wasm(self):
        target = _make_target("https://bank.com")
        static = _make_static(["wasm"], ["navigator.userAgent"])
        result = classify(target, static)
        assert result.level == "extreme"

    def test_returns_recommended_path(self):
        target = _make_target("https://api.com")
        static = _make_static(["subtle", "crypto"], ["canvas"])
        result = classify(target, static)
        assert result.recommended_path in ("rules_only", "static_only", "static+dynamic", "full+human")

    def test_has_reasons(self):
        target = _make_target("https://api.com")
        static = _make_static(["hmac"], [])
        result = classify(target, static)
        assert len(result.reasons) >= 1

    def test_known_pattern_takes_precedence(self):
        from axelo.memory.schema import SitePattern
        target = _make_target("https://known.com")
        static = _make_static(["wasm"], [])  # wasm 本来是 extreme
        pattern = SitePattern(
            domain="known.com",
            algorithm_type="hmac",
            difficulty="medium",
            verified=True,
            success_count=5,
        )
        result = classify(target, static, known_pattern=pattern)
        # 已知记忆库模式优先
        assert result.level == "medium"
        assert "记忆库" in result.reasons[0]
