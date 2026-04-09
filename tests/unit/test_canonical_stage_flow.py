from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from axelo.agents.scanner import ScanReport
from axelo.agents.verifier_agent import VerificationAnalysis
from axelo.config import settings
from axelo.cost import CostBudget, CostRecord
from axelo.models.analysis import AIHypothesis, StaticAnalysis, TokenCandidate
from axelo.models.codegen import GeneratedCode
from axelo.models.pipeline import Decision, PipelineState
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s6_ai_analyze import AIAnalysisStage
from axelo.pipeline.stages.s7_codegen import CodeGenStage
from axelo.pipeline.stages.s8_verify import VerifyStage
from axelo.verification.engine import VerificationResult


class DummyMode:
    name = "auto"

    async def gate(self, decision: Decision, state: PipelineState) -> str:
        if decision.default:
            return decision.default
        if decision.options:
            return decision.options[0]
        return "accept"

    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        return True


def _target(session_id: str) -> TargetSite:
    return TargetSite(
        url="https://example.com/api/search",
        session_id=session_id,
        interaction_goal="collect signed data",
    )


def _static_results() -> dict[str, StaticAnalysis]:
    return {
        "bundle_main": StaticAnalysis(
            bundle_id="bundle_main",
            crypto_imports=["hmac", "sha256"],
            token_candidates=[
                TokenCandidate(
                    func_id="bundle_main:sign",
                    token_type="hmac",
                    confidence=0.91,
                    request_field="X-Sign",
                )
            ],
            string_constants=["HmacSHA256"],
        )
    }


@pytest.mark.asyncio
async def test_ai_analysis_stage_builds_canonical_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    class FakeScannerAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def scan(self, target, static_results):
            return ScanReport(
                bundle_complexity="moderate",
                detected_frameworks=["webpack"],
                crypto_libs=["hmac"],
                interesting_functions=["bundle_main:sign"],
                token_field_hints=["X-Sign"],
                priority_bundles=["bundle_main"],
                quick_verdict="Evidence is sufficient for hypothesis generation.",
                estimated_difficulty="medium",
            )

    class FakeHypothesisAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def generate(self, target, static_results, dynamic, scan_report):
            return AIHypothesis(
                algorithm_description="Build an HMAC over the request path and timestamp.",
                generator_func_ids=["bundle_main:sign"],
                steps=["read timestamp", "sign request path"],
                inputs=["path", "timestamp"],
                outputs={"X-Sign": "hex digest"},
                codegen_strategy="python_reconstruct",
                confidence=0.84,
            )

    monkeypatch.setattr("axelo.pipeline.stages.s6_ai_analyze.ScannerAgent", FakeScannerAgent)
    monkeypatch.setattr("axelo.pipeline.stages.s6_ai_analyze.HypothesisAgent", FakeHypothesisAgent)

    stage = AIAnalysisStage(
        ai_client=MagicMock(),
        cost=CostRecord(session_id="s01"),
        budget=CostBudget(max_usd=1.0),
        retriever=MagicMock(),
    )

    result = await stage.execute(
        PipelineState(session_id="s01"),
        DummyMode(),
        target=_target("s01"),
        static_results=_static_results(),
    )

    assert result.success is True
    analysis = result.next_input["analysis"]
    assert analysis.ai_hypothesis is not None
    assert analysis.signature_spec is not None
    assert analysis.signature_spec.algorithm_id == "hmac"
    assert analysis.signature_spec.codegen_strategy == "python_reconstruct"
    assert (tmp_path / "sessions" / "s01" / "ai_context" / "scan_report.json").exists()
    assert (tmp_path / "sessions" / "s01" / "ai_context" / "hypothesis.json").exists()
    assert (tmp_path / "sessions" / "s01" / "ai_context" / "analysis_result.json").exists()


@pytest.mark.asyncio
async def test_codegen_stage_uses_canonical_codegen_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    class FakeCodeGenAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def generate(self, target, hypothesis, static_results, dynamic, output_dir):
            crawler = output_dir / "crawler.py"
            crawler.write_text("class TokenGenerator:\n    pass\n", encoding="utf-8")
            bridge = output_dir / "bridge_server.js"
            bridge.write_text("console.log('bridge');\n", encoding="utf-8")
            manifest = output_dir / "crawler_manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            requirements = output_dir / "requirements.txt"
            requirements.write_text("# deps\nhttpx==0.28.0\n", encoding="utf-8")
            return {
                "crawler_script": crawler,
                "bridge_server": bridge,
                "manifest": manifest,
                "requirements": requirements,
            }

    monkeypatch.setattr("axelo.pipeline.stages.s7_codegen.CodeGenAgent", FakeCodeGenAgent)

    stage = CodeGenStage(
        ai_client=MagicMock(),
        cost=CostRecord(session_id="s02"),
        budget=CostBudget(max_usd=1.0),
        retriever=MagicMock(),
    )

    result = await stage.execute(
        PipelineState(session_id="s02"),
        DummyMode(),
        hypothesis=AIHypothesis(
            algorithm_description="Use HMAC",
            generator_func_ids=["bundle_main:sign"],
            steps=["sign request"],
            inputs=["path"],
            outputs={"X-Sign": "hex digest"},
            codegen_strategy="js_bridge",
            confidence=0.9,
        ),
        static_results=_static_results(),
        target=_target("s02"),
    )

    assert result.success is True
    generated = result.next_input["generated"]
    assert isinstance(generated, GeneratedCode)
    assert generated.output_mode == "bridge"
    assert generated.crawler_deps == ["httpx==0.28.0"]
    assert generated.crawler_script_path == tmp_path / "sessions" / "s02" / "output" / "crawler.py"
    assert generated.bridge_server_path == tmp_path / "sessions" / "s02" / "output" / "bridge_server.js"


@pytest.mark.asyncio
async def test_codegen_stage_fails_fast_when_crawler_artifact_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    class FakeCodeGenAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def generate(self, target, hypothesis, static_results, dynamic, output_dir):
            manifest = output_dir / "crawler_manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            return {"manifest": manifest}

    monkeypatch.setattr("axelo.pipeline.stages.s7_codegen.CodeGenAgent", FakeCodeGenAgent)

    stage = CodeGenStage(
        ai_client=MagicMock(),
        cost=CostRecord(session_id="s02b"),
        budget=CostBudget(max_usd=1.0),
        retriever=MagicMock(),
    )

    result = await stage.execute(
        PipelineState(session_id="s02b"),
        DummyMode(),
        hypothesis=AIHypothesis(
            algorithm_description="Use HMAC",
            generator_func_ids=["bundle_main:sign"],
            steps=["sign request"],
            inputs=["path"],
            outputs={"X-Sign": "hex digest"},
            codegen_strategy="python_reconstruct",
            confidence=0.9,
        ),
        static_results=_static_results(),
        target=_target("s02b"),
    )

    assert result.success is False
    assert result.error is not None
    assert "produced no crawler script" in result.error
    assert "crawler_manifest.json" in result.error


@pytest.mark.asyncio
async def test_verify_stage_uses_canonical_verifier_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)
    output_dir = tmp_path / "sessions" / "s03" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    crawler = output_dir / "crawler.py"
    crawler.write_text("class TokenGenerator:\n    pass\n", encoding="utf-8")

    class FakeVerifierAgent:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def verify_and_analyze(self, generated, target, hypothesis, live_verify=True):
            verification = VerificationResult(
                ok=True,
                score=1.0,
                attempts=1,
                strategy_used=generated.output_mode,
                report="verification ok",
            )
            return verification, VerificationAnalysis(
                failure_type="wrong_algorithm",
                root_cause="n/a",
                fix_suggestion="n/a",
                retry_strategy="give_up",
                confidence=1.0,
            )

    monkeypatch.setattr("axelo.pipeline.stages.s8_verify.VerifierAgent", FakeVerifierAgent)

    stage = VerifyStage(
        ai_client=MagicMock(),
        cost=CostRecord(session_id="s03"),
        budget=CostBudget(max_usd=1.0),
    )

    generated = GeneratedCode(
        session_id="s03",
        output_mode="standalone",
        crawler_script_path=crawler,
    )
    hypothesis = AIHypothesis(
        algorithm_description="Use HMAC",
        generator_func_ids=["bundle_main:sign"],
        steps=["sign request"],
        inputs=["path"],
        outputs={"X-Sign": "hex digest"},
        codegen_strategy="python_reconstruct",
        confidence=0.9,
    )

    result = await stage.execute(
        PipelineState(session_id="s03"),
        DummyMode(),
        generated=generated,
        target=_target("s03"),
        hypothesis=hypothesis,
    )

    assert result.success is True
    updated = result.next_input["generated"]
    assert updated.verified is True
    assert updated.verification_notes == "verification ok"
    assert (tmp_path / "sessions" / "s03" / "output" / "verify_report.txt").read_text(encoding="utf-8") == "verification ok"
