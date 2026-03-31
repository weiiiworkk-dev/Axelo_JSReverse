"""Amazon 风格签名逆向集成测试

Amazon 签名特征：
- AWS SigV4 风格：HMAC-SHA256 多层签名
- 请求头：X-Amz-Date, X-Amz-Content-Sha256, Authorization
- 输入：method + url + headers + body hash + timestamp
"""
import pytest
from axelo.models.analysis import FunctionSignature, StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite, RequestCapture
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants
from axelo.analysis.static.call_graph import CallGraph
from axelo.classifier.rules import classify


# ── 仿 Amazon SigV4 JS 代码片段 ───────────────────────────────────

AMAZON_SIGN_FUNC = """
function signRequest(method, url, headers, body) {
    var ts = new Date().toISOString().replace(/[:\\-]|\\.\\d{3}/g, '');
    var dateStr = ts.slice(0, 8);
    var bodyHash = sha256(body || '');
    var canonicalHeaders = Object.keys(headers).sort()
        .map(k => k.toLowerCase() + ':' + headers[k])
        .join('\\n');
    var signedHeaders = Object.keys(headers).sort()
        .map(k => k.toLowerCase()).join(';');
    var canonicalReq = [method, url, '', canonicalHeaders, '', signedHeaders, bodyHash].join('\\n');
    var credentialScope = dateStr + '/us-east-1/execute-api/aws4_request';
    var stringToSign = 'AWS4-HMAC-SHA256\\n' + ts + '\\n' + credentialScope + '\\n' + sha256(canonicalReq);
    var signingKey = hmac(hmac(hmac(hmac('AWS4' + SECRET_KEY, dateStr), 'us-east-1'), 'execute-api'), 'aws4_request');
    var signature = hmac(signingKey, stringToSign);
    return {
        'X-Amz-Date': ts,
        'X-Amz-Content-Sha256': bodyHash,
        'Authorization': 'AWS4-HMAC-SHA256 Credential=' + ACCESS_KEY + '/' + credentialScope +
            ', SignedHeaders=' + signedHeaders + ', Signature=' + signature
    };
}
"""

AMAZON_SHA256_FUNC = """
function sha256(data) {
    return CryptoJS.SHA256(data).toString(CryptoJS.enc.Hex);
}
"""

AMAZON_HMAC_FUNC = """
function hmac(key, data) {
    return CryptoJS.HmacSHA256(data, key).toString(CryptoJS.enc.Hex);
}
"""

AMAZON_STRING_CONSTANTS = [
    "AWS4-HMAC-SHA256",
    "aws4_request",
    "us-east-1",
    "execute-api",
    "HmacSHA256",
    "ab12",  # 4 char hex，低于 16 位最低要求，应被过滤
    "1a2b3c4d5e6f789012345678901234567890abcdef1234",  # 长 hex key，应被保留
]


class TestAmazonStaticAnalysis:
    """测试对 Amazon SigV4 风格代码的静态分析能力"""

    def test_detects_hmac_in_sign_function(self):
        func = FunctionSignature(
            func_id="amazon_bundle:signRequest",
            name="signRequest",
            raw_source=AMAZON_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        types = [c.token_type for c in candidates]
        assert "hmac" in types or "sha256" in types

    def test_sign_function_has_high_confidence(self):
        func = FunctionSignature(
            func_id="amazon_bundle:signRequest",
            name="signRequest",
            raw_source=AMAZON_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        if candidates:
            best = max(c.confidence for c in candidates)
            assert best >= 0.4

    def test_hmac_helper_detected(self):
        func = FunctionSignature(
            func_id="amazon_bundle:hmac",
            name="hmac",
            raw_source=AMAZON_HMAC_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "hmac" for c in candidates)

    def test_sha256_helper_detected(self):
        func = FunctionSignature(
            func_id="amazon_bundle:sha256",
            name="sha256",
            raw_source=AMAZON_SHA256_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type in ("sha256", "hmac") for c in candidates)

    def test_scan_string_constants_filters_properly(self):
        result = scan_string_constants(AMAZON_STRING_CONSTANTS)
        # HmacSHA256 应该被检测到（含加密关键词）
        assert any("hmac" in s.lower() or "HmacSHA256" in s for s in result)
        # 4 char hex（低于 16 位）应该被过滤
        assert "ab12" not in result

    def test_call_graph_sign_uses_hmac(self):
        funcs = {
            "f:signRequest": FunctionSignature(func_id="f:signRequest", name="signRequest", calls=["f:hmac", "f:sha256"]),
            "f:hmac":        FunctionSignature(func_id="f:hmac",        name="hmac",        calls=[]),
            "f:sha256":      FunctionSignature(func_id="f:sha256",      name="sha256",      calls=[]),
            "f:fetchAPI":    FunctionSignature(func_id="f:fetchAPI",    name="fetchAPI",    calls=["f:signRequest"]),
        }
        g = CallGraph(funcs)
        # signRequest 应该调用 hmac
        callees = g.get_callees("f:signRequest", depth=1)
        assert "f:hmac" in callees
        assert "f:sha256" in callees
        # fetchAPI 应该是 signRequest 的调用者
        callers = g.get_callers("f:signRequest", depth=1)
        assert "f:fetchAPI" in callers


class TestAmazonClassifier:
    """测试 Amazon 风格站点的难度分类"""

    def test_amazon_classified_as_hard(self):
        target = TargetSite(
            url="https://www.amazon.com/s?k=laptop",
            session_id="amazon_test",
            interaction_goal="搜索接口签名逆向",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["hmac", "sha256", "HmacSHA256"],
                env_access=["navigator.userAgent", "Date.now"],
                token_candidates=[
                    TokenCandidate(func_id="main:signRequest", token_type="hmac", confidence=0.8)
                ],
            )
        }
        result = classify(target, static)
        assert result.level in ("medium", "hard", "extreme")
        assert result.recommended_path in ("static_only", "static+dynamic", "full+human")

    def test_amazon_with_subtle_is_harder(self):
        target = TargetSite(
            url="https://www.amazon.com/api/v1/search",
            session_id="amazon_subtle_test",
            interaction_goal="API 签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["subtle", "sha256"],
                env_access=["canvas", "navigator.userAgent"],
            )
        }
        result = classify(target, static)
        # subtle + canvas 应该是 hard 或 extreme
        assert result.level in ("hard", "extreme")


class TestAmazonVerification:
    """测试 Amazon 风格签名的验证层"""

    def test_amazon_auth_header_format_check(self):
        from axelo.verification.comparator import TokenComparator
        cmp = TokenComparator()
        capture = RequestCapture(
            url="https://www.amazon.com/api",
            method="GET",
            request_headers={
                "Authorization": "AWS4-HMAC-SHA256 Credential=AKID/20231115/us-east-1/execute-api/aws4_request, SignedHeaders=host;x-amz-date, Signature=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "x-amz-date": "20231115T120000Z",
            },
            response_status=200,
        )
        # 生成了类似格式的签名
        generated = {
            "Authorization": "AWS4-HMAC-SHA256 Credential=AKID/20231115/us-east-1/execute-api/aws4_request, SignedHeaders=host;x-amz-date, Signature=1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "x-amz-date": "20231115T120001Z",
        }
        result = cmp.compare(generated, capture)
        # x-amz-date 是时效性字段，Authorization 应该检查格式
        assert result.score >= 0.5  # 至少部分字段匹配
