from __future__ import annotations

from axelo.models.bundle import JSBundle
from axelo.models.execution import ExecutionPlan
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s2_fetch import _apply_bundle_caps


def test_bundle_guardrails_skip_oversized_entries(tmp_path):
    bundles = [
        JSBundle(bundle_id="a", source_url="https://a.js", raw_path=tmp_path / "a.js", size_bytes=120 * 1024, bundle_type="webpack"),
        JSBundle(bundle_id="b", source_url="https://b.js", raw_path=tmp_path / "b.js", size_bytes=700 * 1024, bundle_type="rollup"),
        JSBundle(bundle_id="c", source_url="https://c.js", raw_path=tmp_path / "c.js", size_bytes=140 * 1024, bundle_type="plain"),
        JSBundle(bundle_id="d", source_url="https://d.js", raw_path=tmp_path / "d.js", size_bytes=160 * 1024, bundle_type="plain"),
    ]
    target = TargetSite(url="https://example.com", session_id="s01", interaction_goal="demo")
    target.execution_plan = ExecutionPlan(max_bundles=2, max_bundle_size_kb=256, max_total_bundle_kb=320)

    selected, note = _apply_bundle_caps(bundles, target)
    assert [bundle.bundle_id for bundle in selected] == ["a", "c"]
    assert "skipped" in note
