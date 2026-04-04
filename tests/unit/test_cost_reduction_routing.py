from __future__ import annotations

from types import SimpleNamespace

import pytest

from axelo.agents.codegen_agent import CodeGenAgent
from axelo.agents.scanner import ScanReport
from axelo.config import settings
from axelo.cost import CostBudget, CostRecord
from axelo.models.analysis import AIHypothesis, StaticAnalysis, TokenCandidate
from axelo.models.execution import ExecutionPlan
from axelo.models.pipeline import Decision, PipelineState
from axelo.models.target import RequestCapture, TargetSite
from axelo.pipeline.stages.s6_ai_analyze import AIAnalysisStage
from axelo.storage.analysis_cache import AnalysisCache


class DummyMode:
    async def gate(self, decision: Decision, state: PipelineState) -> str:
        return decision.default or "accept"


@pytest.mark.asyncio
async def test_ai_analysis_stage_supports_scanner_only(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    class FakeScannerAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def scan(self, target, static_results):
            return ScanReport(
                bundle_complexity="moderate",
                detected_frameworks=["webpack"],
                crypto_libs=["hmac"],
                interesting_functions=["bundle:sign"],
                token_field_hints=["X-Sign"],
                priority_bundles=["bundle"],
                quick_verdict="Scanner-only summary is enough.",
                estimated_difficulty="medium",
            )

    class FailHypothesisAgent:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("HypothesisAgent should not be constructed for scanner-only routing")

    monkeypatch.setattr("axelo.pipeline.stages.s6_ai_analyze.ScannerAgent", FakeScannerAgent)
    monkeypatch.setattr("axelo.pipeline.stages.s6_ai_analyze.HypothesisAgent", FailHypothesisAgent)

    target = TargetSite(url="https://example.com", session_id="scan01", interaction_goal="demo")
    target.execution_plan = ExecutionPlan(ai_mode="scanner_only", skip_codegen=True)
    stage = AIAnalysisStage(
        ai_client=SimpleNamespace(_model="claude-haiku-4-5"),
        cost=CostRecord(session_id="scan01"),
        budget=CostBudget(max_usd=1.0),
        retriever=SimpleNamespace(),
    )

    result = await stage.execute(
        PipelineState(session_id="scan01"),
        DummyMode(),
        target=target,
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
    )

    assert result.success is True
    assert result.next_input["hypothesis"] is None
    analysis = result.next_input["analysis"]
    assert analysis.ready_for_codegen is False
    assert analysis.analysis_notes == "Scanner-only summary is enough."


def test_analysis_cache_roundtrip(tmp_path):
    cache = AnalysisCache(tmp_path)
    target = TargetSite(
        url="https://example.com/search",
        session_id="cache01",
        interaction_goal="collect products",
        target_hint="iphone",
        known_endpoint="/api/search",
    )
    target.target_requests = [
        RequestCapture(url="https://example.com/api/search?q=iphone", method="GET"),
    ]
    static_results = {
        "bundle": StaticAnalysis(
            bundle_id="bundle",
            token_candidates=[
                TokenCandidate(func_id="bundle:sign", token_type="hmac", confidence=0.91),
            ],
        )
    }

    cache.save(
        target,
        bundle_hashes=["abc123def456"],
        static_results=static_results,
        signature_family="hmac-sha256-timestamp",
        template_name="hmac-sha256-timestamp",
    )
    hit = cache.lookup(target, ["abc123def456"])

    assert hit is not None
    assert hit.signature_family == "hmac-sha256-timestamp"
    assert hit.static_models()["bundle"].token_candidates[0].token_type == "hmac"


@pytest.mark.asyncio
async def test_codegen_agent_uses_template_without_ai(tmp_path):
    class NoAIClient:
        def __init__(self) -> None:
            self._model = "claude-sonnet-4-6"

        async def analyze(self, **kwargs):
            raise AssertionError("AI analyze should not be called for deterministic template generation")

    class FakeRetriever:
        def get_all_templates(self):
            return [
                SimpleNamespace(
                    name="hmac-sha256-timestamp",
                    algorithm_type="hmac",
                    python_code=(
                        "import hmac, hashlib, time, secrets\n\n"
                        "class TokenGenerator:\n"
                        "    def __init__(self, secret_key: str):\n"
                        "        self.secret_key = secret_key.encode()\n\n"
                        "    def generate(self, url: str, method: str = 'GET', body: str = '', **kwargs) -> dict[str, str]:\n"
                        "        ts = str(int(time.time() * 1000))\n"
                        "        nonce = secrets.token_hex(8)\n"
                        "        sign_str = f'{method.upper()}\\\\n{url}\\\\n{ts}\\\\n{nonce}\\\\n{body}'\n"
                        "        sign = hmac.new(self.secret_key, sign_str.encode(), hashlib.sha256).hexdigest()\n"
                        "        return {'X-Sign': sign, 'X-Timestamp': ts, 'X-Nonce': nonce}\n"
                    ),
                )
            ]

    target = TargetSite(
        url="https://example.com",
        session_id="tmpl01",
        interaction_goal="collect signed data",
    )
    target.target_requests = [
        RequestCapture(
            url="https://example.com/api/search?q=phone",
            method="GET",
            request_headers={"Accept": "application/json"},
        )
    ]
    agent = CodeGenAgent(NoAIClient(), CostRecord(session_id="tmpl01"), CostBudget(max_usd=1.0), retriever=FakeRetriever())
    artifacts = await agent.generate(
        target,
        AIHypothesis(
            algorithm_description="Use HMAC",
            generator_func_ids=["bundle:sign"],
            steps=["sign request"],
            inputs=["url", "method", "body"],
            outputs={"X-Sign": "hex digest"},
            codegen_strategy="python_reconstruct",
            confidence=0.9,
            template_name="hmac-sha256-timestamp",
            secret_candidate="template_secret_value",
        ),
        {"bundle": StaticAnalysis(bundle_id="bundle")},
        None,
        tmp_path,
    )

    crawler = artifacts["crawler_script"].read_text(encoding="utf-8")
    assert "template_secret_value" in crawler
    assert "class ExampleCrawler" in crawler
    assert "TokenGenerator" in crawler
