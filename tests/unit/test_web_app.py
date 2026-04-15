from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from fastapi.testclient import TestClient

from axelo.config import settings
from axelo.engine.models import EnginePlan, EngineRequest, MissionBrief, PreparedRun, PrincipalAgentState, TaskIntent, MissionState
from axelo.utils.session_catalog import SessionCatalog
from axelo.web.server import create_app


def _make_workspace() -> Path:
    root = Path.cwd() / ".tmp_web_tests"
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / f"web-app-{uuid.uuid4().hex[:12]}"
    workspace.mkdir(parents=True, exist_ok=False)
    return workspace


def test_start_mission_uses_principal_runtime_contract(monkeypatch):
    workspace = _make_workspace()
    monkeypatch.setattr(settings, "workspace", workspace)

    watched: list[tuple[str, str]] = []
    attached: list[str] = []
    launched: list[str] = []

    class FakeEngine:
        async def plan_request(self, *, prompt: str, url: str = "", goal: str = "", metadata: dict | None = None, session_id: str = ""):
            request = EngineRequest(prompt=prompt, url=url, goal=goal, metadata=dict(metadata or {}))
            request.metadata["site_code"] = "AAA"
            request.metadata["site_key"] = "example.com"
            return PreparedRun(
                request=request,
                plan=EnginePlan(
                    session_id="AAA-000001",
                    summary="summary",
                    intent=TaskIntent(intent_type="mission_driven", confidence=1.0),
                    lines_of_inquiry=["surface", "transport"],
                ),
                session_id="AAA-000001",
                session_dir=str(workspace / "sessions" / "AAA" / "AAA-000001"),
                principal_state=PrincipalAgentState(
                    mission=MissionState(session_id="AAA-000001", target_url=url, objective=goal),
                ),
                mission_brief=MissionBrief(title="brief", summary="summary"),
            )

    async def fake_run_mission(engine, prepared, broadcaster):
        launched.append(prepared.session_id)

    def fake_attach(engine, broadcaster, session_id: str):
        attached.append(session_id)

    monkeypatch.setattr("axelo.web.routes.mission_intake.UnifiedEngine", FakeEngine)
    monkeypatch.setattr("axelo.web.routes.mission_intake._run_mission", fake_run_mission)
    monkeypatch.setattr("axelo.web.routes.mission_intake.attach_web_hook", fake_attach)

    app = create_app()
    app.state.watcher.watch = lambda session_id, session_dir: watched.append((session_id, str(session_dir)))
    client = TestClient(app)

    response = client.post(
        "/api/mission/start",
        json={
            "url": "https://example.com/search",
            "data_type": "product_data",
            "goal": "",
            "key_fields": [],
            "stealth": "medium",
            "output_format": "sdk",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "AAA-000001"
    assert payload["site_code"] == "AAA"
    assert payload["site_key"] == "example.com"
    assert payload["effective_goal"]
    assert attached == ["AAA-000001"]
    assert watched == []
    assert launched == ["AAA-000001"]
    shutil.rmtree(workspace, ignore_errors=True)


def test_sessions_api_reads_nested_site_sessions(monkeypatch):
    workspace = _make_workspace()
    monkeypatch.setattr(settings, "workspace", workspace)
    sessions_root = workspace / "sessions"
    catalog = SessionCatalog(sessions_root)
    allocation = catalog.allocate(url_or_host="https://example.com")

    request_path = allocation.session_dir / "session_request.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    site_code = allocation.site_code
    session_id = allocation.session_id
    request_path.write_text(
        json.dumps(
            {
                "url": "https://example.com",
                "goal": "Collect listing data",
                "metadata": {"site_key": "example.com", "site_code": site_code},
            }
        ),
        encoding="utf-8",
    )
    final_dir = allocation.session_dir / "artifacts" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "mission_report.json").write_text(
        json.dumps(
            {
                "site_key": "example.com",
                "site_code": site_code,
                "mission_status": "success",
                "mission_outcome": "mechanism_validated",
                "success": True,
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "artifact_index.json").write_text(json.dumps({"artifacts": []}), encoding="utf-8")
    logs_dir = allocation.session_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "principal_state.json").write_text(json.dumps({"mission": {"session_id": session_id}}), encoding="utf-8")

    client = TestClient(create_app())
    list_response = client.get("/api/sessions")
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["site_key"] == "example.com"
    assert sessions[0]["site_code"] == site_code

    detail_response = client.get(f"/api/sessions/{session_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["request"]["url"] == "https://example.com"
    assert detail["mission_report"]["mission_status"] == "success"
    shutil.rmtree(workspace, ignore_errors=True)
