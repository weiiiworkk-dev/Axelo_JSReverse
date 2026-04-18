from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from fastapi.testclient import TestClient

from axelo.config import settings
from axelo.engine.models import EnginePlan, EngineRequest, MissionBrief, PreparedRun, PrincipalAgentState, TaskIntent, MissionState
from axelo.models.contracts import MissionContract, ReadinessAssessment
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


def test_workbench_session_endpoints_create_thread_and_messages(monkeypatch):
    workspace = _make_workspace()
    monkeypatch.setattr(settings, "workspace", workspace)

    class FakeProcessor:
        async def process_message(self, message, contract, history):
            updated = MissionContract.model_validate(contract.model_dump(mode="json"))
            updated.target_url = "https://example.com"
            updated.objective = "Collect product data"
            updated.readiness_assessment = ReadinessAssessment(
                confidence=0.92,
                is_ready=True,
                assessed_at="2026-04-18T12:00:00",
            )
            return {
                "ai_reply": "Router has enough context to prepare the run.",
                "updated_contract": updated,
                "readiness": updated.readiness_assessment,
            }

    monkeypatch.setattr("axelo.web.routes.sessions.IntakeAIProcessor", FakeProcessor)

    client = TestClient(create_app())

    create_response = client.post("/api/sessions")
    assert create_response.status_code == 200
    session = create_response.json()
    session_id = session["session_id"]

    detail_response = client.get(f"/api/sessions/{session_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["thread_items"] == []

    message_response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={"message": "Inspect example.com and capture product titles."},
    )
    assert message_response.status_code == 200
    payload = message_response.json()
    assert payload["session"]["ready_to_run"] is True
    assert len(payload["session"]["thread_items"]) == 2
    assert payload["session"]["thread_items"][0]["kind"] == "user_message"
    assert payload["session"]["thread_items"][1]["kind"] == "router_message"

    thread_response = client.get(f"/api/sessions/{session_id}/thread")
    assert thread_response.status_code == 200
    thread = thread_response.json()
    assert thread["session_id"] == session_id
    assert [item["kind"] for item in thread["items"]] == ["user_message", "router_message"]
    shutil.rmtree(workspace, ignore_errors=True)


def test_run_events_and_checkpoint_routes_follow_workbench_contract(monkeypatch):
    workspace = _make_workspace()
    monkeypatch.setattr(settings, "workspace", workspace)
    sessions_root = workspace / "sessions"
    catalog = SessionCatalog(sessions_root)
    allocation = catalog.allocate(url_or_host="https://example.com")
    run_id = allocation.session_id

    request_payload = {
        "url": "https://example.com",
        "goal": "Collect listing data",
        "metadata": {"site_key": "example.com", "site_code": allocation.site_code},
    }
    allocation.session_dir.mkdir(parents=True, exist_ok=True)
    (allocation.session_dir / "session_request.json").write_text(json.dumps(request_payload), encoding="utf-8")

    final_dir = allocation.session_dir / "artifacts" / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    (final_dir / "mission_report.json").write_text(
        json.dumps(
            {
                "objective": "Collect listing data",
                "mission_status": "running",
                "updated_at": "2026-04-18T12:00:00",
            }
        ),
        encoding="utf-8",
    )
    (final_dir / "artifact_index.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "name": "crawler.py",
                        "path": str(final_dir / "crawler.py"),
                        "category": "script",
                        "description": "Generated crawler script",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    logs_dir = allocation.session_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_id": "evt-1",
                        "seq": 1,
                        "published_at": "2026-04-18T12:00:00",
                        "kind": "mission",
                        "message": "Router started the run.",
                        "data": {},
                    }
                ),
                json.dumps(
                    {
                        "event_id": "evt-2",
                        "seq": 2,
                        "published_at": "2026-04-18T12:00:02",
                        "kind": "dispatch",
                        "message": "Browser agent is inspecting the target surface.",
                        "data": {"objective": "discover_surface"},
                    }
                ),
                json.dumps(
                    {
                        "event_id": "evt-3",
                        "seq": 3,
                        "published_at": "2026-04-18T12:00:04",
                        "kind": "verdict",
                        "message": "Surface inspection completed with a stable route.",
                        "data": {"objective": "discover_surface"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app())

    run_response = client.get(f"/api/runs/{run_id}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["run_id"] == run_id
    assert run_payload["artifacts"][0]["artifact_type"] == "script"

    events_response = client.get(f"/api/runs/{run_id}/events")
    assert events_response.status_code == 200
    events_payload = events_response.json()
    assert events_payload["next_cursor"] == 3
    assert [event["kind"] for event in events_payload["events"]] == [
        "run.created",
        "agent.activity",
        "deliverable.created",
    ]

    approve_response = client.post(f"/api/runs/{run_id}/checkpoints/cp-1/approve")
    assert approve_response.status_code == 200
    checkpoint = approve_response.json()["checkpoint"]
    assert checkpoint["status"] == "approved"

    checkpoints_response = client.get(f"/api/runs/{run_id}/checkpoints")
    assert checkpoints_response.status_code == 200
    checkpoints = checkpoints_response.json()["checkpoints"]
    assert checkpoints[0]["checkpoint_id"] == "cp-1"
    assert checkpoints[0]["status"] == "approved"
    shutil.rmtree(workspace, ignore_errors=True)
