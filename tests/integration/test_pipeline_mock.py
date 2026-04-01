"""端对端流水线集成测试（全 mock，不发真实网络请求）

测试目标：
- 静态分析 → 分类 → BM25 检索 → 验证层 的完整数据流
- 所有 IO（网络/浏览器/AI）全部 mock
- 覆盖 easy/medium/hard 三种难度路径
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from axelo.models.analysis import FunctionSignature, StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite, RequestCapture
from axelo.analysis.static.pattern_matcher import score_function
from axelo.analysis.static.call_graph import CallGraph
from axelo.classifier.rules import classify
from axelo.verification.comparator import TokenComparator


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def simple_hmac_target():
    return TargetSite(
        url="https://api.example.com/search",
        session_id="pipe_test_01",
        interaction_goal="搜索接口 HMAC 签名",
    )


@pytest.fixture
def simple_hmac_capture():
    return RequestCapture(
        url="https://api.example.com/search",
        method="POST",
        request_headers={
            "x-sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "x-timestamp": "1700000000000",
            "x-nonce": "a1b2c3d4e5f6g7h8",
            "content-type": "application/json",
        },
        response_status=200,
    )


@pytest.fixture
def simple_hmac_static():
    return {
        "bundle_main": StaticAnalysis(
            bundle_id="bundle_main",
            crypto_imports=["hmac", "sha256"],
            env_access=["Date.now"],
            token_candidates=[
                TokenCandidate(
                    func_id="bundle_main:signRequest",
                    token_type="hmac",
                    confidence=0.82,
                    evidence=["包含关键词 'hmac'", "函数名含 sign"],
                    request_field="X-Sign",
                ),
                TokenCandidate(
                    func_id="bundle_main:getTimestamp",
                    token_type="timestamp",
                    confidence=0.9,
                    evidence=["包含关键词 'Date.now'"],
                    request_field="X-Timestamp",
                ),
            ],
            string_constants=["HmacSHA256", "1234567890abcdef1234567890abcdef"],
        )
    }


@pytest.fixture
def fingerprint_target():
    return TargetSite(
        url="https://secure-shop.example.com/api/cart",
        session_id="pipe_test_02",
        interaction_goal="购物车接口带指纹签名",
    )


@pytest.fixture
def fingerprint_static():
    return {
        "bundle_main": StaticAnalysis(
            bundle_id="bundle_main",
            crypto_imports=["hmac", "sha256", "md5"],
            env_access=["canvas", "webgl", "navigator.userAgent"],
            token_candidates=[
                TokenCandidate(
                    func_id="bundle_main:signRequest",
                    token_type="hmac",
                    confidence=0.75,
                    request_field="X-Sign",
                ),
                TokenCandidate(
                    func_id="bundle_main:getFingerprint",
                    token_type="fingerprint",
                    confidence=0.8,
                    request_field="X-Device-ID",
                ),
            ],
        )
    }


# ── 测试：Static Analysis → Classifier 数据流 ─────────────────────

class TestStaticToClassifierFlow:
    """测试从静态分析到分类器的完整数据流"""

    def test_hmac_pipeline_medium_difficulty(self, simple_hmac_target, simple_hmac_static):
        result = classify(simple_hmac_target, simple_hmac_static)
        assert result.level in ("medium", "hard")
        assert result.score >= 20
        assert len(result.reasons) >= 1

    def test_fingerprint_pipeline_hard_difficulty(self, fingerprint_target, fingerprint_static):
        result = classify(fingerprint_target, fingerprint_static)
        assert result.level in ("hard", "extreme")
        assert result.recommended_path in ("static+dynamic", "full+human")

    def test_empty_bundle_is_not_easy(self):
        """空 bundle（无候选函数）应该因混淆判断得分更高"""
        target = TargetSite(
            url="https://obfuscated.example.com/api",
            session_id="pipe_obf_test",
            interaction_goal="高度混淆站点",
        )
        static = {
            "bundle": StaticAnalysis(
                bundle_id="bundle",
                crypto_imports=[],
                env_access=[],
                token_candidates=[],  # 无候选
                function_map={},       # 无函数
            )
        }
        result = classify(target, static)
        # 无候选函数 → 额外加 15 分
        assert result.score >= 15

    def test_pipeline_score_reflects_multiple_signals(self):
        """多个 hard 信号应该累加得分"""
        target = TargetSite(
            url="https://multi-signal.example.com",
            session_id="pipe_multi_test",
            interaction_goal="测试多信号累加",
        )
        static = {
            "bundle": StaticAnalysis(
                bundle_id="bundle",
                crypto_imports=["subtle", "rsa"],
                env_access=["canvas", "webgl", "fingerprint"],
            )
        }
        result = classify(target, static)
        # canvas(15) + webgl(15) + fingerprint(15) + subtle(15) + rsa(15) = 75 → hard/extreme
        assert result.level in ("hard", "extreme")
        assert result.score >= 50


# ── 测试：Pattern Matcher → Call Graph → Comparator 数据流 ─────────

class TestAnalysisToVerificationFlow:
    """测试分析结果到验证层的数据流"""

    def test_end_to_end_hmac_detection_and_format_check(
        self, simple_hmac_capture
    ):
        """
        完整流程：
        1. 从 JS 代码检测 HMAC 候选
        2. 构建调用图
        3. 生成符合格式的测试签名
        4. 用 Comparator 验证格式
        """
        # Step 1: 静态特征识别
        sign_func = FunctionSignature(
            func_id="main:signRequest",
            name="signRequest",
            raw_source="var sig = hmac(key, ts + nonce + url); return {sign: sig, ts: ts}",
        )
        candidates = score_function(sign_func, {})
        assert any(c.token_type == "hmac" for c in candidates)

        # Step 2: 调用图确认
        funcs = {
            "f:buildHeaders": FunctionSignature(
                func_id="f:buildHeaders", name="buildHeaders",
                calls=["f:signRequest", "f:getNonce"]
            ),
            "f:signRequest": FunctionSignature(
                func_id="f:signRequest", name="signRequest",
                calls=["f:hmacSHA256"]
            ),
            "f:getNonce": FunctionSignature(func_id="f:getNonce", name="getNonce", calls=[]),
            "f:hmacSHA256": FunctionSignature(func_id="f:hmacSHA256", name="hmacSHA256", calls=[]),
        }
        g = CallGraph(funcs)
        path = g.shortest_path("f:buildHeaders", "f:hmacSHA256")
        assert path is not None

        # Step 3: 生成测试签名（模拟生成代码输出）
        generated = {
            "x-sign": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",  # 64 hex
            "x-timestamp": "1700000001000",  # 时效性字段
        }

        # Step 4: 格式验证
        cmp = TokenComparator()
        result = cmp.compare(generated, simple_hmac_capture)
        assert result.score == 1.0  # 两个字段都应该格式匹配

    def test_comparator_handles_extra_generated_fields(self, simple_hmac_capture):
        """生成结果比 ground truth 多出字段时应检测为 missing"""
        cmp = TokenComparator()
        generated = {
            "x-sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "x-timestamp": "1700000001000",
            "x-extra-field": "some-extra-value",  # GT 里没有
        }
        result = cmp.compare(generated, simple_hmac_capture)
        assert "x-extra-field" in result.missing

    def test_comparator_score_partial_match(self):
        """部分字段匹配时得分应该是部分分"""
        cmp = TokenComparator()
        capture = RequestCapture(
            url="https://api.test.com",
            method="GET",
            request_headers={
                "x-sign": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "x-session": "sessiontoken123456",
            },
            response_status=200,
        )
        generated = {
            "x-sign": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "x-wrong-field": "something",  # GT 里没有
        }
        result = cmp.compare(generated, capture)
        assert 0.0 < result.score < 1.0


# ── 测试：Memory DB 在 Pipeline 中的作用 ─────────────────────────

class TestMemoryInPipeline:
    """测试记忆库在流水线中的检索和存储"""

    def test_known_site_skips_to_template(self, tmp_path):
        """已知站点应该直接用模板，跳过复杂分析"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.schema import SitePattern
        from axelo.classifier.rules import classify

        db = MemoryDB(tmp_path / "test.db")
        # 预先保存已知站点
        db.save_site_pattern(SitePattern(
            domain="known-site.com",
            algorithm_type="hmac",
            difficulty="medium",
            verified=True,
            success_count=5,
        ))

        target = TargetSite(
            url="https://known-site.com/api",
            session_id="known_test",
            interaction_goal="已知站点测试",
        )
        static = {
            "bundle": StaticAnalysis(
                bundle_id="bundle",
                crypto_imports=["wasm"],  # wasm 本来是 extreme
                env_access=[],
            )
        }
        pattern = db.get_site_pattern("known-site.com")
        result = classify(target, static, known_pattern=pattern)
        assert result.level == "medium"  # 已知模式覆盖 wasm 判断

    def test_session_write_and_read(self, tmp_path):
        """会话写入后能正确读取"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.schema import ReverseSession

        db = MemoryDB(tmp_path / "test.db")
        session = ReverseSession(
            session_id="test_session_001",
            url="https://shopee.sg/api/v2/search",
            domain="shopee.sg",
            goal="搜索接口签名",
            difficulty="hard",
            algorithm_type="hmac",
            verified=True,
            ai_confidence=0.85,
            experience_summary="Shopee 使用 HMAC-SHA256 对 partner_id+path+timestamp 签名，密钥为 partner_key",
        )
        db.save_session(session)
        rows = db.get_similar_sessions("shopee.sg")
        assert len(rows) >= 1
        assert rows[0].algorithm_type == "hmac"

    def test_bundle_cache_deduplication(self, tmp_path):
        """相同内容 hash 的 bundle 只缓存一次"""
        from axelo.memory.db import MemoryDB
        from axelo.memory.schema import JSBundleCache

        db = MemoryDB(tmp_path / "test.db")
        cache1 = JSBundleCache(
            content_hash="abc123def456abc1",
            bundle_type="webpack",
            algorithm_type="hmac",
            token_candidate_count=3,
        )
        cache2 = JSBundleCache(
            content_hash="abc123def456abc1",  # 相同 hash
            bundle_type="webpack",
            algorithm_type="hmac",
            token_candidate_count=5,  # 更新的数据
        )
        db.save_bundle_cache(cache1)
        db.save_bundle_cache(cache2)

        retrieved = db.get_bundle_cache("abc123def456abc1")
        assert retrieved is not None
        assert retrieved.token_candidate_count == 5  # 应该是更新后的值


# ── 测试：VerificationEngine 无真实请求 ──────────────────────────

class TestVerificationEnginePipeline:
    """验证引擎在流水线中的完整行为"""

    @pytest.mark.asyncio
    async def test_hmac_script_generates_and_verifies(self, tmp_path):
        """完整生成 → 验证流程（live_verify=False）"""
        from axelo.verification.engine import VerificationEngine
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite

        script = tmp_path / "token_generator.py"
        script.write_text('''
import hmac as _hmac
import hashlib
import time
import secrets

class TokenGenerator:
    def __init__(self):
        self.secret = b"shopee_partner_key_example"

    def generate(self, url="", method="GET", body="", **kwargs):
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(8)
        msg = f"{method.upper()}\\n{url}\\n{ts}\\n{nonce}".encode()
        sign = _hmac.new(self.secret, msg, hashlib.sha256).hexdigest()
        return {
            "X-Sign": sign,
            "X-Timestamp": ts,
            "X-Nonce": nonce,
        }
''', encoding="utf-8")

        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="shopee_pipe_test",
            output_mode="standalone",
            crawler_script_path=script,
        )
        target = TargetSite(
            url="https://shopee.sg/api/v2/search",
            session_id="shopee_pipe_test",
            interaction_goal="搜索签名",
        )
        result = await engine.verify(generated, target, live_verify=False)
        assert result.attempts >= 1

    @pytest.mark.asyncio
    async def test_missing_generator_class_fails_gracefully(self, tmp_path):
        """脚本存在但没有 TokenGenerator 类时应该优雅失败"""
        from axelo.verification.engine import VerificationEngine
        from axelo.models.codegen import GeneratedCode
        from axelo.models.target import TargetSite

        script = tmp_path / "bad_script.py"
        script.write_text('''
# 没有 TokenGenerator 类
def some_function():
    return {"sign": "abc"}
''', encoding="utf-8")

        engine = VerificationEngine()
        generated = GeneratedCode(
            session_id="bad_script_test",
            output_mode="standalone",
            crawler_script_path=script,
        )
        target = TargetSite(
            url="https://api.example.com",
            session_id="bad_script_test",
            interaction_goal="test",
        )
        result = await engine.verify(generated, target, live_verify=False)
        assert not result.ok
