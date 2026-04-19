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
