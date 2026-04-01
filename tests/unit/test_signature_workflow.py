from __future__ import annotations

from axelo.analysis import build_signature_spec
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, HookIntercept, StaticAnalysis, TokenCandidate
from axelo.models.target import TargetSite
from axelo.orchestrator.workflow_runtime import WorkflowRuntime
from axelo.storage import WorkflowStore


def test_build_signature_spec_promotes_browser_dependencies():
    target = TargetSite(url="https://example.com", session_id="s01", interaction_goal="demo", requires_login=True)
    static = StaticAnalysis(
        bundle_id="b01",
        token_candidates=[TokenCandidate(func_id="b01:sign", token_type="hmac", confidence=0.9)],
        env_access=["window.canvas", "navigator.userAgent"],
    )
    dynamic = DynamicAnalysis(
        bundle_id="b01",
        hook_intercepts=[HookIntercept(api_name="crypto.subtle.sign", args_repr="[]", return_repr="sig")],
        crypto_primitives=["crypto.subtle.sign"],
    )
    hypothesis = AIHypothesis(
        algorithm_description="Use HMAC with timestamp",
        generator_func_ids=["b01:sign"],
        steps=["collect timestamp", "compute hmac"],
        inputs=["timestamp", "path"],
        outputs={"X-Sign": "hex digest"},
        codegen_strategy="python_reconstruct",
        confidence=0.8,
    )

    spec = build_signature_spec(target, hypothesis, {"b01": static}, dynamic)
    assert spec.algorithm_id == "hmac"
    assert spec.codegen_strategy == "js_bridge"
    assert "window.canvas" in spec.browser_dependencies


def test_workflow_runtime_manual_review_checkpoint(tmp_path):
    runtime = WorkflowRuntime(WorkflowStore(tmp_path))
    trace = runtime.load_or_create("s01")
    updated = runtime.request_manual_review("s01", trace, "difficulty", "Extreme target")
    assert updated.checkpoints[-1].manual_review is True
    assert updated.checkpoints[-1].stage_name == "difficulty"
