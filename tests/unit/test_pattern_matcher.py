"""静态分析模式匹配单元测试"""
import pytest
from axelo.models.analysis import FunctionSignature
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants


def _make_func(name: str, source: str) -> FunctionSignature:
    return FunctionSignature(
        func_id=f"bundle01:{name}",
        name=name,
        raw_source=source,
    )


class TestScoreFunction:
    def test_detects_hmac(self):
        func = _make_func("signRequest", "var sig = hmac(key, data); return sig;")
        candidates = score_function(func, {})
        assert any(c.token_type == "hmac" for c in candidates)
        assert any(c.confidence > 0.3 for c in candidates)

    def test_detects_md5(self):
        func = _make_func("getSign", "return md5(params + salt);")
        candidates = score_function(func, {})
        assert any(c.token_type == "md5" for c in candidates)

    def test_detects_sha256(self):
        func = _make_func("buildToken", "const hash = sha256(input); return hash;")
        candidates = score_function(func, {})
        assert any(c.token_type in ("sha256", "hmac") for c in candidates)

    def test_function_name_boosts_confidence(self):
        # 名字中有 "sign" 的函数应该比普通函数置信度更高
        func_named = _make_func("signRequest", "return hmac(key, data);")
        func_anon = _make_func("processData", "return hmac(key, data);")
        cands_named = score_function(func_named, {})
        cands_anon = score_function(func_anon, {})
        if cands_named and cands_anon:
            best_named = max(c.confidence for c in cands_named)
            best_anon = max(c.confidence for c in cands_anon)
            assert best_named >= best_anon

    def test_no_match_returns_empty(self):
        func = _make_func("renderPage", "document.getElementById('app').innerHTML = html;")
        candidates = score_function(func, {})
        assert candidates == []

    def test_infers_request_field(self):
        func = _make_func("getSign", "return hmac(key, ts + nonce);")
        candidates = score_function(func, {})
        hmac_cands = [c for c in candidates if c.token_type == "hmac"]
        if hmac_cands:
            # 函数名含 sign，应推断 X-Sign 字段
            assert any(c.request_field is not None for c in hmac_cands)

    def test_base64_detection(self):
        func = _make_func("encode", "return btoa(data);")
        candidates = score_function(func, {})
        assert any(c.token_type == "base64" for c in candidates)


class TestScanStringConstants:
    def test_detects_base64_strings(self):
        strings = ["aGVsbG8gd29ybGQ=", "normal text", "SGVsbG8="]
        result = scan_string_constants(strings)
        assert "aGVsbG8gd29ybGQ=" in result

    def test_detects_hex_key(self):
        strings = ["1234567890abcdef1234567890abcdef"]
        result = scan_string_constants(strings)
        assert len(result) >= 1

    def test_filters_short_strings(self):
        strings = ["ab", "cd", "ef"]
        result = scan_string_constants(strings)
        assert result == []

    def test_detects_crypto_keyword_strings(self):
        strings = ["HmacSHA256", "AES-CBC", "normal-string"]
        result = scan_string_constants(strings)
        assert any("hmac" in s.lower() or "aes" in s.lower() for s in result)
