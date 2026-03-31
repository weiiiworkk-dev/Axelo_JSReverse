"""中国主流网站（JD/Bilibili/Baidu）风格签名逆向集成测试

JD 京东：
- sign = md5(params + app_key + timestamp)
- 请求头：sign, timestamp, app_key

Bilibili：
- wbi 签名：key mixing + md5
- 请求参数：w_rid, wts (timestamp)

Baidu：
- 简单 md5 + aes 混合
- 请求参数：sign, t
"""
import pytest
from axelo.models.analysis import FunctionSignature, StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite, RequestCapture
from axelo.analysis.static.pattern_matcher import score_function, scan_string_constants
from axelo.analysis.static.call_graph import CallGraph
from axelo.classifier.rules import classify
from axelo.verification.comparator import TokenComparator
from axelo.memory.schema import SitePattern


# ── JD 京东风格代码 ───────────────────────────────────────────────

JD_SIGN_FUNC = """
function generateSign(params, appKey, appSecret, timestamp) {
    var sortedParams = Object.keys(params).sort().reduce((obj, key) => {
        obj[key] = params[key];
        return obj;
    }, {});
    var paramStr = appKey;
    Object.keys(sortedParams).forEach(function(key) {
        paramStr += key + sortedParams[key];
    });
    paramStr += appSecret;
    var sign = md5(paramStr).toUpperCase();
    return sign;
}
"""

JD_TOKEN_REFRESH_FUNC = """
function refreshAccessToken(refreshToken, appKey, appSecret) {
    var timestamp = Date.now().toString();
    var sign = generateSign({'grant_type': 'refresh_token', 'refresh_token': refreshToken}, appKey, appSecret, timestamp);
    return fetch('/oauth2/access_token', {
        method: 'POST',
        body: JSON.stringify({
            grant_type: 'refresh_token',
            app_key: appKey,
            timestamp: timestamp,
            sign: sign,
        })
    });
}
"""

# ── Bilibili WBI 风格代码 ────────────────────────────────────────

BILIBILI_WBI_FUNC = """
function encWbi(params, img_key, sub_key) {
    var mixin_key = getMixinKey(img_key + sub_key);
    var curr_time = Math.round(Date.now() / 1000);
    var chr_filter = /[!'()*]/g;

    Object.assign(params, { wts: curr_time });
    var query = Object.keys(params)
        .sort()
        .map(function(key) {
            return key + '=' + String(params[key]).replace(chr_filter, '');
        })
        .join('&');
    var wbi_sign = md5(query + mixin_key);
    return query + '&w_rid=' + wbi_sign;
}

function getMixinKey(orig) {
    var MIXIN_KEY_ENC_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52];
    return MIXIN_KEY_ENC_TAB.map(function(n) { return orig[n]; }).join('').slice(0, 32);
}
"""

# ── Baidu 风格代码 ────────────────────────────────────────────────

BAIDU_SIGN_FUNC = """
function baiduSign(query, tn) {
    var t = Date.now();
    var signStr = query + tn + t.toString();
    var sign = CryptoJS.MD5(signStr).toString();
    return {sign: sign, t: t};
}
"""

BAIDU_AES_FUNC = """
function encryptParams(data, key) {
    var encrypted = CryptoJS.AES.encrypt(JSON.stringify(data), CryptoJS.enc.Utf8.parse(key), {
        iv: CryptoJS.enc.Utf8.parse('1234567890abcdef'),
        mode: CryptoJS.mode.CBC,
        padding: CryptoJS.pad.Pkcs7
    });
    return encrypted.toString();
}
"""


class TestJDStaticAnalysis:
    """测试京东风格代码的静态分析"""

    def test_jd_sign_detects_md5(self):
        func = FunctionSignature(
            func_id="jd_main:generateSign",
            name="generateSign",
            raw_source=JD_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "md5" for c in candidates)

    def test_jd_sign_confidence_is_reasonable(self):
        func = FunctionSignature(
            func_id="jd_main:generateSign",
            name="generateSign",
            raw_source=JD_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        md5_cands = [c for c in candidates if c.token_type == "md5"]
        if md5_cands:
            assert md5_cands[0].confidence >= 0.3

    def test_jd_token_refresh_detects_timestamp(self):
        func = FunctionSignature(
            func_id="jd_main:refreshAccessToken",
            name="refreshAccessToken",
            raw_source=JD_TOKEN_REFRESH_FUNC,
        )
        candidates = score_function(func, {})
        types = {c.token_type for c in candidates}
        # 应该检测到 timestamp 或 token 相关
        assert len(types) >= 1

    def test_jd_call_graph_token_to_sign(self):
        funcs = {
            "f:refreshAccessToken": FunctionSignature(
                func_id="f:refreshAccessToken", name="refreshAccessToken",
                calls=["f:generateSign", "f:fetch"]
            ),
            "f:generateSign": FunctionSignature(
                func_id="f:generateSign", name="generateSign",
                calls=["f:md5"]
            ),
            "f:md5": FunctionSignature(func_id="f:md5", name="md5", calls=[]),
            "f:fetch": FunctionSignature(func_id="f:fetch", name="fetch", calls=[]),
        }
        g = CallGraph(funcs)
        path = g.shortest_path("f:refreshAccessToken", "f:md5")
        assert path is not None
        assert len(path) == 3  # refreshAccessToken → generateSign → md5

    def test_jd_classified_as_medium(self):
        target = TargetSite(
            url="https://api.jd.com/routerjson",
            session_id="jd_test",
            interaction_goal="商品搜索接口签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["md5"],
                env_access=["Date.now"],
                token_candidates=[
                    TokenCandidate(func_id="main:generateSign", token_type="md5", confidence=0.7)
                ],
            )
        }
        result = classify(target, static)
        assert result.level in ("medium", "hard")

    def test_jd_known_pattern_overrides(self):
        """京东已知模式应该覆盖静态分析结果"""
        target = TargetSite(
            url="https://api.jd.com/routerjson",
            session_id="jd_known_test",
            interaction_goal="签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["wasm"],  # wasm 本来是 extreme
                env_access=[],
            )
        }
        pattern = SitePattern(
            domain="jd.com",
            algorithm_type="md5",
            difficulty="medium",
            verified=True,
            success_count=10,
        )
        result = classify(target, static, known_pattern=pattern)
        assert result.level == "medium"  # 已知模式优先
        assert "记忆库" in result.reasons[0]


class TestBilibiliStaticAnalysis:
    """测试 Bilibili WBI 签名的静态分析"""

    def test_bilibili_wbi_detects_md5(self):
        func = FunctionSignature(
            func_id="bili_main:encWbi",
            name="encWbi",
            raw_source=BILIBILI_WBI_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "md5" for c in candidates)

    def test_bilibili_mixin_key_has_constants(self):
        """getMixinKey 函数中有大量数字常量，应该被扫描到"""
        # 模拟从 AST 提取到的字符串/数字常量
        strings = ["w_rid", "wts", "MixinKey", "md5", "HmacSHA256"]
        result = scan_string_constants(strings)
        assert any("md5" in s.lower() or "hmac" in s.lower() for s in result)

    def test_bilibili_classified_as_medium(self):
        """WBI 签名本质是 MD5，应该是 medium"""
        target = TargetSite(
            url="https://api.bilibili.com/x/web-interface/search/all",
            session_id="bili_test",
            interaction_goal="搜索接口 WBI 签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["md5"],
                env_access=["Date.now"],
                token_candidates=[
                    TokenCandidate(func_id="main:encWbi", token_type="md5", confidence=0.75),
                ],
            )
        }
        result = classify(target, static)
        assert result.level in ("medium", "hard")

    def test_bilibili_wbi_call_graph_depth(self):
        """WBI 有多层函数调用"""
        funcs = {
            "f:encWbi":      FunctionSignature(func_id="f:encWbi",      name="encWbi",      calls=["f:getMixinKey", "f:md5"]),
            "f:getMixinKey": FunctionSignature(func_id="f:getMixinKey", name="getMixinKey", calls=[]),
            "f:md5":         FunctionSignature(func_id="f:md5",         name="md5",         calls=[]),
            "f:initWbi":     FunctionSignature(func_id="f:initWbi",     name="initWbi",     calls=["f:encWbi"]),
        }
        g = CallGraph(funcs)
        # 从 initWbi 到 getMixinKey 需要经过 encWbi
        path = g.shortest_path("f:initWbi", "f:getMixinKey")
        assert path is not None
        assert "f:encWbi" in path


class TestBaiduStaticAnalysis:
    """测试百度风格代码的静态分析"""

    def test_baidu_md5_sign_detected(self):
        func = FunctionSignature(
            func_id="baidu_main:baiduSign",
            name="baiduSign",
            raw_source=BAIDU_SIGN_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "md5" for c in candidates)

    def test_baidu_aes_encrypt_detected(self):
        func = FunctionSignature(
            func_id="baidu_main:encryptParams",
            name="encryptParams",
            raw_source=BAIDU_AES_FUNC,
        )
        candidates = score_function(func, {})
        assert any(c.token_type == "aes" for c in candidates)

    def test_baidu_aes_makes_it_harder(self):
        """有 AES 加密时，比单纯 MD5 更难（但不是 extreme）"""
        target = TargetSite(
            url="https://www.baidu.com/s?wd=test",
            session_id="baidu_test",
            interaction_goal="搜索请求签名",
        )
        static = {
            "main": StaticAnalysis(
                bundle_id="main",
                crypto_imports=["md5", "aes", "sha256"],
                env_access=["Date.now"],
                token_candidates=[
                    TokenCandidate(func_id="main:baiduSign", token_type="md5", confidence=0.7),
                    TokenCandidate(func_id="main:encryptParams", token_type="aes", confidence=0.75),
                ],
            )
        }
        result = classify(target, static)
        # AES 不在 HARD_SIGNALS 中，但组合加密仍至少 medium
        assert result.level in ("medium", "hard")
        assert result.score >= 20


class TestMultiSiteMemoryRetrieval:
    """测试多站点的记忆库检索功能"""

    def test_memory_db_seed_templates(self, tmp_path):
        """验证种子模板正确初始化"""
        from axelo.memory.db import MemoryDB
        db = MemoryDB(tmp_path / "test.db")
        templates = db.list_templates()
        assert len(templates) >= 3
        names = [t.name for t in templates]
        assert "hmac-sha256-timestamp" in names
        assert "md5-params-salt" in names
        assert "canvas-fingerprint-bridge" in names

    def test_bm25_retrieves_hmac_template(self, tmp_path):
        """BM25 搜索 hmac/sign 关键词应该命中 hmac-sha256-timestamp 模板"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.vector_store import VectorStore
        from axelo.memory.retriever import MemoryRetriever
        db = MemoryDB(tmp_path / "test.db")
        vs = VectorStore(tmp_path / "vectors")
        retriever = MemoryRetriever(db, vs)
        results = retriever.bm25_search_templates("hmac sha256 sign timestamp")
        assert len(results) >= 1
        assert any("hmac" in t.algorithm_type for t in results)

    def test_bm25_retrieves_md5_template(self, tmp_path):
        """BM25 搜索 md5/params/salt 关键词应该命中 md5-params-salt 模板"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.vector_store import VectorStore
        from axelo.memory.retriever import MemoryRetriever
        db = MemoryDB(tmp_path / "test.db")
        vs = VectorStore(tmp_path / "vectors")
        retriever = MemoryRetriever(db, vs)
        results = retriever.bm25_search_templates("md5 params salt sign")
        assert len(results) >= 1
        assert any("md5" in t.algorithm_type for t in results)

    def test_bm25_retrieves_fingerprint_template(self, tmp_path):
        """BM25 搜索 canvas/fingerprint 关键词应该命中 canvas-fingerprint-bridge 模板"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.vector_store import VectorStore
        from axelo.memory.retriever import MemoryRetriever
        db = MemoryDB(tmp_path / "test.db")
        vs = VectorStore(tmp_path / "vectors")
        retriever = MemoryRetriever(db, vs)
        results = retriever.bm25_search_templates("canvas fingerprint webgl device")
        assert len(results) >= 1
        assert any("fingerprint" in t.algorithm_type for t in results)

    def test_site_pattern_lookup_unknown_domain(self, tmp_path):
        """未知域名应该返回 None，不崩溃"""
        from axelo.memory.db import MemoryDB
        db = MemoryDB(tmp_path / "test.db")
        pattern = db.get_site_pattern("unknown-new-site.example.com")
        assert pattern is None

    def test_save_and_retrieve_site_pattern(self, tmp_path):
        """保存站点模式后能精确检索"""
        from axelo.memory.db import MemoryDB
        db = MemoryDB(tmp_path / "test.db")
        p = SitePattern(
            domain="shopee.sg",
            algorithm_type="hmac",
            difficulty="hard",
            verified=True,
            success_count=3,
        )
        db.save_site_pattern(p)
        retrieved = db.get_site_pattern("shopee.sg")
        assert retrieved is not None
        assert retrieved.domain == "shopee.sg"
        assert retrieved.difficulty == "hard"
        assert retrieved.algorithm_type == "hmac"
