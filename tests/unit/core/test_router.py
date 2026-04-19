from __future__ import annotations
import pytest
import asyncio
from axelo.core.router.registry import AgentRegistry
from axelo.core.base_agent import BaseAgent
from axelo.core.models import SubTask, AgentResult, ResultStatus


class FakeReconAgent(BaseAgent):
    name = "recon"
    async def execute(self, task: SubTask) -> AgentResult:
        return AgentResult(agent="recon", status=ResultStatus.SUCCESS, data={"antibot": "none"})


def test_registry_register_and_get():
    reg = AgentRegistry()
    reg.register(FakeReconAgent())
    agent = reg.get("recon")
    assert agent is not None
    assert agent.name == "recon"


def test_registry_get_missing_raises():
    reg = AgentRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent")


def test_registry_list_agents():
    reg = AgentRegistry()
    reg.register(FakeReconAgent())
    assert "recon" in reg.list_agents()


from axelo.core.router.monitor import Monitor, MonitorDecision
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import TaskGraph, SubTask
from axelo.core.router.state_machine import StateMachine, SessionStatus


def test_monitor_success_continues():
    sm = StateMachine()
    for s in [SessionStatus.SESSION_PLANNING, SessionStatus.SESSION_RUNNING,
              SessionStatus.RECON_QUEUED, SessionStatus.RECON_RUNNING]:
        sm.transition(s)

    result = AgentResult(agent="recon", status=ResultStatus.SUCCESS, data={"antibot": "cloudflare"})
    graph = TaskGraph(tasks=[
        SubTask(agent="recon", objective="profile"),
        SubTask(agent="browser", objective="fetch", depends_on=["recon"]),
    ])
    graph.tasks[0].mark_running()
    graph.tasks[0].mark_complete(result)

    monitor = Monitor()
    decision = monitor.evaluate(agent="recon", result=result, graph=graph, sm=sm)
    assert decision == MonitorDecision.CONTINUE


def test_monitor_verification_failure_triggers_recodegen():
    sm = StateMachine()
    for s in [SessionStatus.SESSION_PLANNING, SessionStatus.SESSION_RUNNING,
              SessionStatus.CODEGEN_QUEUED, SessionStatus.CODEGEN_GENERATING,
              SessionStatus.CODEGEN_COMPLETE, SessionStatus.VERIFICATION_QUEUED,
              SessionStatus.VERIFICATION_RUNNING]:
        sm.transition(s)

    result = AgentResult(agent="verification", status=ResultStatus.FAILURE, error="hash_mismatch")
    graph = TaskGraph(tasks=[
        SubTask(agent="codegen", objective="gen"),
        SubTask(agent="verification", objective="verify", depends_on=["codegen"]),
    ])
    monitor = Monitor()
    decision = monitor.evaluate(agent="verification", result=result, graph=graph, sm=sm)
    assert decision == MonitorDecision.REQUEUE_CODEGEN


# Task 5: Planner
from unittest.mock import AsyncMock, patch
from axelo.core.router.planner import Planner
from axelo.core.models import TaskGraph


def test_planner_returns_task_graph():
    mock_response = """
    [
      {"agent": "recon", "objective": "Profile the site", "depends_on": []},
      {"agent": "browser", "objective": "Fetch JS bundles", "depends_on": ["recon"]},
      {"agent": "analysis", "objective": "Analyze JS", "depends_on": ["browser"]}
    ]
    """
    with patch("axelo.core.router.planner.Planner._call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_response
        planner = Planner()
        graph = asyncio.run(planner.plan(
            target_url="https://example.com",
            objective="Extract auth token"
        ))
    assert isinstance(graph, TaskGraph)
    assert len(graph.tasks) == 3
    agents = [t.agent for t in graph.tasks]
    assert "recon" in agents
    assert "browser" in agents


# Task 6: Router orchestrator
from axelo.core.router.router import Router


class FakeBrowserAgent(BaseAgent):
    name = "browser"
    async def execute(self, task: SubTask) -> AgentResult:
        return AgentResult(agent="browser", status=ResultStatus.SUCCESS, data={"bundles": 3})


def _make_registry():
    reg = AgentRegistry()
    reg.register(FakeReconAgent())
    reg.register(FakeBrowserAgent())
    return reg


def test_router_runs_full_session(tmp_path):
    mock_graph_json = """[
        {"agent": "recon", "objective": "profile", "depends_on": []},
        {"agent": "browser", "objective": "fetch", "depends_on": ["recon"]}
    ]"""
    with patch("axelo.core.router.planner.Planner._call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_graph_json
        router = Router(registry=_make_registry(), artifacts_root=tmp_path)
        result = asyncio.run(router.run(
            target_url="https://example.com",
            objective="get token",
        ))
    assert result["status"] == "complete"
    assert "session_id" in result
    assert (tmp_path / result["session_id"]).is_dir()
