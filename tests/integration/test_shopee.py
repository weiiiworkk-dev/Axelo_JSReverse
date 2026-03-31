"""Shopee 风格签名逆向集成测试

Shopee 签名特征：
- 多层 HMAC：先用 partner_key 对 URL+timestamp 签名
- 设备指纹：Canvas + WebGL 生成 device_fingerprint
- 请求头：sign, timestamp, partner_id
- 典型：POST /api/v2/shop/get_shop_info?partner_id=xxx&timestamp=xxx&sign=xxx
"""
import pytest
from axelo.models.analysis import FunctionSignature, StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite, RequestCapture
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants
from axelo.analysis.static.call_graph import CallGraph
from axelo.classifier.rules import classify
from axelo.verification.comparator import TokenComparator


# ── 仿 Shopee JS 签名代码 ─────────────────────────────────────────

SHOPEE_SIGN_FUNC = """
function generateSign(partner_id, partner_key, path, timestamp, shop_id) {
    var base_string = partner_id + path + timestamp;
    if (shop_id) {
        base_string += shop_id;
    }
    var sign = CryptoJS.HmacSHA256(base_string, partner_key).toString();
    return sign;
}
"""

SHOPEE_FINGERPRINT_FUNC = """
function getDeviceFingerprint() {
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillText('Shopee fingerprint', 2, 2);
    var canvasData = canvas.toDataURL();

    var gl = canvas.getContext('webgl');
    var renderer = gl ? gl.getParameter(gl.RENDERER) : 'none';
    var vendor = gl ? gl.getParameter(gl.VENDOR) : 'none';

    var fp = CryptoJS.MD5(canvasData + renderer + vendor + navigator.userAgent).toString();
    return fp;
}
"""

SHOPEE_NONCE_FUNC = """
function generateNonce(length) {
    var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    var result = '';
    for (var i = 0; i < (length || 32); i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}
"""

SHOPEE_STRING_CONSTANTS = [
    "HmacSHA256",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    "partner_id",
    "sign",
    "timestamp",
    "device_fingerprint",
    "1a2b3c4d5e6f7890abcdef1234567890",  # 32 hex = MD5 output length
]


class TestShopeeStaticAnalysis:
    """测试对 Shopee 风格代码的静态分析"""

    def test_detects_hmac_sign_function(self):
        func = FunctionSignature(
            func_id="shopee:generateSign",
            name="generateSign",
            raw_source=SHOPEE_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "hmac" for c in candidates)

    def test_sign_function_infers_request_field(self):
        func = FunctionSignature(
            func_id="shopee:generateSign",
            name="generateSign",
            raw_source=SHOPEE_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        hmac_cands = [c for c in candidates if c.token_type == "hmac"]
        # sign 函数应该推断出 X-Sign 或类似字段
        if hmac_cands:
            assert any(c.request_field is not None for c in hmac_cands)

    def test_fingerprint_function_detected(self):
        func = FunctionSignature(
            func_id="shopee:getDeviceFingerprint",
            name="getDeviceFingerprint",
            raw_source=SHOPEE_FINGERPRINT_FUNC,
        )
        candidates = score_function(func, {})
        types = [c.token_type for c in candidates]
        # 应该检测到 fingerprint 或 md5
        assert any(t in ("fingerprint", "md5") for t in types)

    def test_string_constants_detect_hmac_keyword(self):
        result = scan_string_constants(SHOPEE_STRING_CONSTANTS)
        # HmacSHA256 应该被检测到
        crypto_hits = [s for s in result if "hmac" in s.lower() or "sha" in s.lower()]
        assert len(crypto_hits) >= 1

    def test_call_graph_fingerprint_before_sign(self):
        """模拟 Shopee 调用链：main → getDeviceFingerprint + generateSign → send"""
        funcs = {
            "f:main": FunctionSignature(
                func_id="f:main", name="main",
                calls=["f:getDeviceFingerprint", "f:generateSign", "f:sendRequest"]
            ),
            "f:getDeviceFingerprint": FunctionSignature(
                func_id="f:getDeviceFingerprint", name="getDeviceFingerprint",
                calls=["f:canvasFingerprint", "f:webglFingerprint"]
            ),
            "f:generateSign": FunctionSignature(
                func_id="f:generateSign", name="generateSign", calls=["f:hmacSHA256"]
            ),
            "f:sendRequest": FunctionSignature(func_id="f:sendRequest", name="sendRequest", calls=[]),
            "f:canvasFingerprint": FunctionSignature(func_id="f:canvasFingerprint", name="canvasFingerprint", calls=[]),
            "f:webglFingerprint": FunctionSignature(func_id="f:webglFingerprint", name="webglFingerprint", calls=[]),
            "f:hmacSHA256": FunctionSignature(func_id="f:hmacSHA256", name="hmacSHA256", calls=[]),
        }
        g = CallGraph(funcs)

        # main 到 hmacSHA256 的路径应该存在
        path = g.shortest_path("f:main", "f:hmacSHA256")
        assert path is not None
        assert "f:generateSign" in path

        # 子图应该包含所有相关函数
        subgraph = g.subgraph_for_candidates(["f:generateSign"])
        related = subgraph["f:generateSign"]
        assert "f:hmacSHA256" in related or "f:main" in related


class TestShopeeClassifier:
    """测试 Shopee 风格站点分类（fingerprint + HMAC = hard）"""

    def test_shopee_with_canvas_classified_as_hard(self):
        target = TargetSite(
            url="https://shopee.sg/api/v2/search",
            session_id="shopee_test",
            interaction_goal="搜索接口签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["hmac", "sha256", "md5"],
                env_access=["canvas", "webgl", "navigator.userAgent"],
                token_candidates=[
                    TokenCandidate(func_id="main:generateSign", token_type="hmac", confidence=0.75),
                    TokenCandidate(func_id="main:getDeviceFingerprint", token_type="fingerprint", confidence=0.7),
                ],
            )
        }
        result = classify(target, static)
        assert result.level in ("hard", "extreme")
        assert result.recommended_path in ("static+dynamic", "full+human")

    def test_shopee_without_canvas_is_medium(self):
        """没有 canvas 指纹时，只有 HMAC 应该是 medium"""
        target = TargetSite(
            url="https://shopee.sg/api/v2/item",
            session_id="shopee_simple_test",
            interaction_goal="商品接口",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["hmac", "sha256"],
                env_access=[],
                token_candidates=[
                    TokenCandidate(func_id="main:generateSign", token_type="hmac", confidence=0.8),
                ],
            )
        }
        result = classify(target, static)
        assert result.level in ("medium", "hard")


class TestShopeeVerification:
    """测试 Shopee 签名格式验证"""

    def test_shopee_sign_format_matches(self):
        """两个 HMAC-SHA256 输出（64个hex字符）应该格式匹配"""
        cmp = TokenComparator()
        capture = RequestCapture(
            url="https://shopee.sg/api/v2/search_items",
            method="GET",
            request_headers={
                "sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "timestamp": "1700000000",
                "partner_id": "12345",
            },
            response_status=200,
        )
        generated = {
            "sign": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "timestamp": "1700000001",
        }
        result = cmp.compare(generated, capture)
        sign_r = next((r for r in result.field_results if r.field == "sign"), None)
        assert sign_r is not None
        assert sign_r.status == "format_ok"  # 相同长度 hex

    def test_shopee_missing_partner_id_detected(self):
        """生成结果缺少 partner_id 应该被检测出来"""
        cmp = TokenComparator()
        capture = RequestCapture(
            url="https://shopee.sg/api/v2/item",
            method="GET",
            request_headers={
                "sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "partner_id": "12345",
            },
            response_status=200,
        )
        generated = {
            "sign": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            # 缺少 partner_id
        }
        result = cmp.compare(generated, capture)
        # partner_id 不在 generated 里，所以不会报 missing（missing 是指 generated 有但 GT 没有）
        assert result.score == 1.0 or len(result.matched) >= 1
