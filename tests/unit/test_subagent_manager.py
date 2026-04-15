from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from axelo.config import settings
from axelo.engine.subagents import ROLE_MAP, SubAgentManager
from axelo.tools.base import ToolResult, ToolStatus


@pytest.fixture()
def isolated_workspace(monkeypatch):
    workspace = Path.cwd() / ".tmp_subagents_test"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "workspace", workspace)
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_subagent_manager_uses_direct_tool_execution(monkeypatch, isolated_workspace):
    manager = SubAgentManager()
    manager.attach_session(session_id="AAA-000123", initial_input={"url": "https://example.com"})

    async def fake_execute_tool(self, tool_name, input_data=None):
        assert tool_name == "browser"
        assert input_data["url"] == "https://example.com"
        return ToolResult(tool_name=tool_name, status=ToolStatus.SUCCESS, output={"page_url": input_data["url"]})

    monkeypatch.setattr("axelo.engine.subagents.ToolExecutor.execute_tool", fake_execute_tool)

    dispatch = await manager.execute_task(
        tool_name="browser",
        initial_input={"url": "https://example.com"},
        task_params={},
    )

    assert dispatch.agent_role == ROLE_MAP["browser"]
    assert dispatch.result.success is True
    assert dispatch.result.output["page_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_protocol_agent_recovers_primary_surface(isolated_workspace):
    manager = SubAgentManager()
    manager.attach_session(session_id="AAA-000124", initial_input={"url": "https://example.com"})

    dispatch = await manager.execute_task(
        tool_name="protocol",
        initial_input={"url": "https://example.com"},
        task_params={
            "observed_requests": [
                {
                    "url": "https://example.com/api/search?q=mouse&nonce=abc123",
                    "method": "POST",
                    "request_headers": {"x-csrf-token": "abc", "content-type": "application/json"},
                    "request_body": {"token": "signed", "page": 1},
                    "response_status": 200,
                    "response_headers": {"content-type": "application/json"},
                }
            ],
        },
    )

    assert dispatch.result.success is True
    assert dispatch.result.output["target_request_method"] == "POST"
    assert "x-csrf-token" in dispatch.result.output["required_headers"]
    assert "nonce" in dispatch.result.output["required_query_fields"]
    assert "token" in dispatch.result.output["required_body_fields"]


@pytest.mark.asyncio
async def test_response_schema_agent_extracts_embedded_json(isolated_workspace):
    manager = SubAgentManager()
    manager.attach_session(session_id="AAA-000125", initial_input={"url": "https://example.com"})

    dispatch = await manager.execute_task(
        tool_name="response_schema",
        initial_input={"url": "https://example.com"},
        task_params={
            "html_content": """
            <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"items":[{"title":"Mouse","price":"19.99","url":"/p/1"}]}}}
            </script>
            """
        },
    )

    assert dispatch.result.success is True
    assert dispatch.result.output["listing_item_fields"] == ["title", "price", "url"]
    assert dispatch.result.output["field_examples"]["title"] == "Mouse"


@pytest.mark.asyncio
async def test_extraction_agent_maps_fields_from_schema(isolated_workspace):
    manager = SubAgentManager()
    manager.attach_session(session_id="AAA-000126", initial_input={"goal": "Collect product listing data"})

    dispatch = await manager.execute_task(
        tool_name="extraction",
        initial_input={"goal": "Collect product listing data"},
        task_params={
            "response_schema": {
                "schema_fields": ["items.title", "items.url", "items.price"],
                "listing_item_fields": ["title", "url", "price"],
                "field_examples": {"title": "Mouse", "url": "/p/1", "price": "19.99"},
            },
            "requirements_meta": {"fields": ["title", "price", "url"]},
        },
    )

    assert dispatch.result.success is True
    assert dispatch.result.output["coverage"] == 1.0
    assert [item["resolved_path"] for item in dispatch.result.output["mapped_fields"]] == ["title", "price", "url"]


@pytest.mark.asyncio
async def test_execute_objective_aggregates_tool_results(monkeypatch, isolated_workspace):
    manager = SubAgentManager()
    manager.attach_session(
        session_id="AAA-000127",
        initial_input={
            "url": "https://example.com",
            "response_schema": {
                "schema_fields": ["items.title", "items.price", "items.url"],
                "listing_item_fields": ["title", "price", "url"],
            },
            "requirements_meta": {"fields": ["title", "price", "url"]},
        },
    )

    async def fake_execute_task(*, tool_name, initial_input, task_params):
        outputs = {
            "extraction": {"coverage": 1.0, "mapped_fields": [{"requested_field": "title", "resolved_path": "items.title"}]},
            "codegen": {"python_code": "print('crawler')\n", "manifest": {"target_url": "https://example.com"}},
        }
        result = ToolResult(tool_name=tool_name, status=ToolStatus.SUCCESS, output=outputs[tool_name])
        manager._executor.state.save_result(result)
        manager._executor.ctx.add_result(tool_name, result)
        return type(
            "Dispatch",
            (),
            {
                "tool_name": tool_name,
                "agent_role": ROLE_MAP[tool_name],
                "result": result,
            },
        )()

    monkeypatch.setattr(manager, "execute_task", fake_execute_task)

    report = await manager.execute_objective(
        objective="build_artifacts",
        objective_id="objective:build",
        initial_input={"url": "https://example.com"},
        task_params={},
    )

    assert report.success is True
    assert set(report.tool_results) == {"extraction", "codegen"}
    assert "python_code" in report.outputs
    assert len(report.evidence) == 2
