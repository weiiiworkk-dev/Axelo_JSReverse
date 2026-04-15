from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from axelo.config import settings
from axelo.engine.models import AgentReport, EvidenceRecord
from axelo.engine.runtime import UnifiedEngine
from axelo.memory.db import MemoryDB


def _report(objective: str, *, success: bool = True) -> AgentReport:
    mapping = {
        "discover_surface": [
            EvidenceRecord(
                evidence_id="surface-1",
                kind="browser",
                source_task="objective:surface",
                summary="Recovered page surface and bundle references.",
                confidence=0.9,
                details={"page_title": "Example", "js_bundles": ["https://example.com/app.js"]},
            )
        ],
        "recover_transport": [
            EvidenceRecord(
                evidence_id="transport-1",
                kind="protocol",
                source_task="objective:transport",
                summary="Recovered guarded fields and target request.",
                confidence=0.9,
                details={"target_request_url": "https://example.com/api/list", "request_fields": ["token"], "required_headers": ["x-token"]},
            )
        ],
        "recover_static_mechanism": [
            EvidenceRecord(
                evidence_id="reverse-1",
                kind="static",
                source_task="objective:reverse",
                summary="Recovered signature hints from static assets.",
                confidence=0.9,
                details={"algorithms": ["sha256"], "signature_candidates": [{"type": "sha256"}]},
            )
        ],
        "recover_runtime_mechanism": [
            EvidenceRecord(
                evidence_id="runtime-1",
                kind="runtime_hook",
                source_task="objective:runtime",
                summary="Linked runtime-sensitive fields to hook points.",
                confidence=0.9,
                details={"runtime_sensitive_fields": ["token"], "hook_points": ["fetch"]},
            )
        ],
        "recover_response_schema": [
            EvidenceRecord(
                evidence_id="schema-1",
                kind="response_schema",
                source_task="objective:schema",
                summary="Recovered listing schema.",
                confidence=0.9,
                details={"schema_fields": ["items.title", "items.price"], "listing_item_fields": ["title", "price"], "field_examples": {"title": "Mouse"}},
            )
        ],
        "build_artifacts": [
            EvidenceRecord(
                evidence_id="extract-1",
                kind="extraction",
                source_task="objective:build",
                summary="Mapped requested fields.",
                confidence=1.0,
                details={"coverage": 1.0, "mapped_fields": [{"requested_field": "title", "resolved_path": "items.title"}]},
            ),
            EvidenceRecord(
                evidence_id="build-1",
                kind="codegen",
                source_task="objective:build",
                summary="Generated crawler artifacts.",
                confidence=0.9,
                details={"python_code": "print('crawler')\n", "manifest": {"target_url": "https://example.com"}},
            ),
        ],
        "verify_execution": [
            EvidenceRecord(
                evidence_id="verify-1",
                kind="verify",
                source_task="objective:verify",
                summary="Verification passed with mechanism validation.",
                confidence=1.0,
                details={"success": True, "execution_verdict": "pass", "mechanism_verdict": "validated"},
            )
        ],
    }
    outputs = {
        "discover_surface": {"browser": {"page_title": "Example", "js_bundles": ["https://example.com/app.js"]}},
        "build_artifacts": {
            "extraction": {"coverage": 1.0, "mapped_fields": [{"requested_field": "title", "resolved_path": "items.title"}]},
            "codegen": {"python_code": "print('crawler')\n", "manifest": {"target_url": "https://example.com"}},
        },
        "verify_execution": {"verify": {"success": True, "execution_verdict": "pass", "mechanism_verdict": "validated"}},
    }
    return AgentReport(
        run_id=f"{objective}:1",
        objective_id=f"objective:{objective}",
        objective=objective,
        capability=objective,
        agent_role=f"{objective}-agent",
        success=success,
        summary=f"{objective} completed",
        claims=[f"{objective} claim"],
        evidence=mapping.get(objective, []),
        outputs={key: value for key, value in outputs.get(objective, {}).items()},
        tool_results=outputs.get(objective, {}),
        recommended_questions=[],
        duration_seconds=0.1,
    )


@pytest.mark.asyncio
async def test_unified_engine_writes_mission_driven_artifacts(monkeypatch):
    workspace = Path.cwd() / ".tmp_engine_test"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace", workspace)

    async def fake_execute_objective(self, *, objective, objective_id, initial_input, task_params):
        return _report(objective)

    monkeypatch.setattr("axelo.engine.subagents.SubAgentManager.execute_objective", fake_execute_objective)

    engine = UnifiedEngine(workspace=workspace)
    prepared = await engine.plan_request(
        prompt="Collect product listing data and reverse any request signing required",
        url="https://example.com",
        goal="Collect product listing data and reverse any request signing required",
    )
    result = await engine.execute_prepared(prepared)

    session_root = Path(prepared.session_dir)
    assert prepared.session_id == "example_com-000001"
    assert session_root == workspace / "sessions" / "example_com" / "example_com-000001"
    assert result.success is True
    assert result.execution_success is True
    assert result.mission_brief is not None
    assert (workspace / "sessions" / "example_com" / "site.json").exists()
    assert (session_root / "session_request.json").exists()
    assert (session_root / "artifacts" / "final" / "mission_brief.json").exists()
    assert (session_root / "logs" / "principal_state.json").exists()
    assert (session_root / "artifacts" / "final" / "mission_report.json").exists()
    assert (session_root / "artifacts" / "final" / "evidence_graph.json").exists()
    assert (session_root / "artifacts" / "final" / "artifact_index.json").exists()
    assert (session_root / "artifacts" / "generated" / "crawler.py").exists()
    assert (session_root / "artifacts" / "final" / "verify_output.json").exists()
    assert not (session_root / "plan.json").exists()
    assert not (session_root / "artifacts" / "reverse" / "reverse_summary.json").exists()
    assert not (session_root / "artifacts" / "collected" / "crawl_summary.json").exists()

    memory_db = MemoryDB(workspace / "memory" / "engine_memory.db")
    rows = memory_db.get_sessions_by_ids([prepared.session_id])
    assert rows and rows[0].verified is True

    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_plan_request_bootstraps_mission_brief(monkeypatch):
    workspace = Path.cwd() / ".tmp_engine_plan_test"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace", workspace)

    engine = UnifiedEngine(workspace=workspace)
    prepared = await engine.plan_request(
        prompt="collect listing data",
        url="https://example.com",
        goal="collect listing data",
    )

    assert prepared.session_id == "example_com-000001"
    assert prepared.mission_brief is not None
    assert prepared.plan.lines_of_inquiry == prepared.mission_brief.lines_of_inquiry
    assert prepared.principal_state is not None
    assert prepared.principal_state.mission.current_focus == "frame the mission and gather first-hand evidence"

    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_session_codes_reuse_site_code_and_increment_versions(monkeypatch):
    workspace = Path.cwd() / ".tmp_engine_catalog_test"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace", workspace)

    engine = UnifiedEngine(workspace=workspace)

    first = await engine.plan_request(prompt="first", url="https://example.com", goal="first")
    second = await engine.plan_request(prompt="second", url="https://www.example.com/search", goal="second")
    third = await engine.plan_request(prompt="third", url="https://shop.testsite.net", goal="third")
    fourth = await engine.plan_request(prompt="fourth", url="https://portal.another-site.org", goal="fourth")

    assert first.session_id == "example_com-000001"
    assert second.session_id == "example_com-000002"
    assert third.session_id == "testsite_net-000001"
    assert fourth.session_id == "another_site_org-000001"
    assert Path(second.session_dir) == workspace / "sessions" / "example_com" / "example_com-000002"
    assert Path(third.session_dir) == workspace / "sessions" / "testsite_net" / "testsite_net-000001"
    assert Path(fourth.session_dir) == workspace / "sessions" / "another_site_org" / "another_site_org-000001"

    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_unified_engine_halts_after_repeated_non_progressing_objectives(monkeypatch):
    workspace = Path.cwd() / ".tmp_engine_stall_test"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace", workspace)

    attempts = {"recover_response_schema": 0}

    async def fake_execute_objective(self, *, objective, objective_id, initial_input, task_params):
        if objective != "recover_response_schema":
            return _report(objective)

        attempts[objective] += 1
        if attempts[objective] == 1:
            return AgentReport(
                run_id=f"{objective}:1",
                objective_id=objective_id,
                objective=objective,
                capability="schema",
                agent_role="schema-agent",
                success=True,
                summary="recover_response_schema completed using response_schema.",
                claims=["Recovered 0 schema fields and 0 listing fields."],
                evidence=[
                    EvidenceRecord(
                        evidence_id="schema-weak-1",
                        kind="response_schema",
                        source_task=objective_id,
                        summary="Recovered 0 schema fields and 0 listing fields.",
                        confidence=0.4,
                        details={"schema_fields": [], "listing_item_fields": [], "confidence": 0.4},
                    )
                ],
                outputs={"response_schema": {"schema_fields": [], "listing_item_fields": [], "confidence": 0.4}},
                tool_results={"response_schema": {"schema_fields": [], "listing_item_fields": [], "confidence": 0.4}},
                recommended_questions=[],
                duration_seconds=0.1,
            )

        return AgentReport(
            run_id=f"{objective}:{attempts[objective]}",
            objective_id=objective_id,
            objective=objective,
            capability="schema",
            agent_role="schema-agent",
            success=False,
            summary="recover_response_schema stalled using no tools.",
            claims=[],
            counterevidence=["No actionable tool path was selected for this objective."],
            evidence=[],
            outputs={},
            tool_results={},
            recommended_questions=[],
            duration_seconds=0.1,
        )

    monkeypatch.setattr("axelo.engine.subagents.SubAgentManager.execute_objective", fake_execute_objective)

    engine = UnifiedEngine(workspace=workspace)
    prepared = await engine.plan_request(
        prompt="Collect product listing data and reverse any request signing required",
        url="https://example.com",
        goal="Collect product listing data and reverse any request signing required",
    )
    result = await engine.execute_prepared(prepared)

    assert result.principal_state is not None
    # Schema recovery: attempt 1 (weak), attempt 2 (fail → stall=1)
    # Schema bypass fires (build not yet done) → build_artifacts
    # Post-build: schema still < 0.55, stalled, build done → challenge_findings x2 → halt
    assert attempts["recover_response_schema"] == 2
    assert len(result.agent_results) == 9
    assert result.principal_state.mission.status == "failed"
    assert "Mission halted after repeated non-progressing objectives." in result.principal_state.worklog
    assert result.principal_state.next_action_hint == "challenge_findings"

    shutil.rmtree(workspace, ignore_errors=True)
