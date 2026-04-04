from __future__ import annotations

from pathlib import Path

from axelo.models.codegen import GeneratedCode
from axelo.models.execution import ExecutionTier, VerificationMode
from axelo.models.target import TargetSite
from axelo.planner import Planner
from axelo.storage.adapter_registry import AdapterRegistry


def test_planner_prefers_verified_adapter_registry_hit(tmp_path):
    registry = AdapterRegistry(tmp_path)
    script = tmp_path / "crawler.py"
    script.write_text("def crawl():\n    return []\n", encoding="utf-8")
    manifest = tmp_path / "crawler_manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    seed_target = TargetSite(
        url="https://example.com/api",
        session_id="seed",
        interaction_goal="collect products",
        known_endpoint="/api/products",
        output_format="json_file",
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )
    generated = GeneratedCode(
        session_id="seed",
        output_mode="standalone",
        crawler_script_path=script,
        manifest_path=manifest,
    )
    registry.register(seed_target, generated, analysis=None, verified=True)

    planner = Planner(registry)
    target = TargetSite(
        url="https://example.com/search",
        session_id="run01",
        interaction_goal="collect products",
        known_endpoint="/api/products",
        output_format="json_file",
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )
    decision = planner.build(target, budget_usd=1.0)
    assert decision.plan.tier == ExecutionTier.ADAPTER_REUSE
    assert decision.plan.adapter_hit is True
    assert decision.adapter is not None


def test_planner_uses_light_browser_mode_for_known_endpoint_and_low_budget(tmp_path):
    planner = Planner(AdapterRegistry(tmp_path))
    target = TargetSite(
        url="https://example.com/search",
        session_id="run02",
        interaction_goal="collect products",
        known_endpoint="/api/products",
        output_format="json_file",
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )
    decision = planner.build(target, budget_usd=0.25)
    assert decision.plan.tier == ExecutionTier.BROWSER_LIGHT
    assert decision.plan.verification_mode == VerificationMode.BASIC
    assert decision.plan.enable_trace_capture is False


def test_planner_routes_extreme_profile_to_manual_review(tmp_path):
    planner = Planner(AdapterRegistry(tmp_path))
    target = TargetSite(
        url="https://example.com/search",
        session_id="run03",
        interaction_goal="collect products",
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )
    target.site_profile.difficulty_hint = "extreme"
    decision = planner.build(target, budget_usd=1.0)
    assert decision.plan.tier == ExecutionTier.MANUAL_REVIEW
    assert decision.plan.requires_browser is False


def test_planner_disables_executable_replay_when_not_authorized(tmp_path):
    planner = Planner(AdapterRegistry(tmp_path))
    target = TargetSite(
        url="https://example.com/search",
        session_id="run04",
        interaction_goal="collect products",
        authorization_status="pending",
        replay_mode="discover_only",
    )

    decision = planner.build(target, budget_usd=1.0)

    assert decision.plan.skip_codegen is True
    assert decision.plan.verification_mode == VerificationMode.NONE
    assert decision.plan.enable_action_flow is False
    assert decision.plan.should_persist_adapter is False
    assert decision.plan.ai_mode == "scanner_only"
    assert decision.plan.route_label == "scanner_only"
    assert decision.plan.enable_trace_capture is False


def test_planner_prefers_light_tier_when_endpoint_and_hint_are_grounded(tmp_path):
    planner = Planner(AdapterRegistry(tmp_path))
    target = TargetSite(
        url="https://example.com/search?q=phone",
        session_id="run05",
        interaction_goal="collect products",
        target_hint="iphone 15",
        known_endpoint="/api/search",
        requires_login=False,
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )

    decision = planner.build(target, budget_usd=1.0)

    assert decision.plan.tier == ExecutionTier.BROWSER_LIGHT


def test_adapter_registry_materializes_files(tmp_path):
    registry = AdapterRegistry(tmp_path)
    script = tmp_path / "crawler.py"
    script.write_text("def crawl():\n    return []\n", encoding="utf-8")
    manifest = tmp_path / "crawler_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    session_state = tmp_path / "session_state.json"
    session_state.write_text("{}", encoding="utf-8")

    target = TargetSite(
        url="https://example.com/api",
        session_id="seed",
        interaction_goal="collect products",
        known_endpoint="/api/products",
    )
    generated = GeneratedCode(
        session_id="seed",
        output_mode="standalone",
        crawler_script_path=script,
        manifest_path=manifest,
        session_state_path=session_state,
    )
    record = registry.register(target, generated, analysis=None, verified=True)
    assert record is not None

    output_dir = tmp_path / "out"
    materialized = registry.materialize(record, output_dir)
    assert materialized.crawler_script_path == output_dir / script.name
    assert materialized.manifest_path == output_dir / manifest.name
    assert materialized.session_state_path == output_dir / session_state.name
    assert Path(materialized.crawler_script_path).exists()
