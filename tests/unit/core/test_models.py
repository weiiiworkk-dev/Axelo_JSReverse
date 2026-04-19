from __future__ import annotations
import pytest
from axelo.core.models.task import SubTask, TaskGraph, TaskStatus


def test_subtask_defaults():
    t = SubTask(agent="browser", objective="fetch JS bundle")
    assert t.status == TaskStatus.PENDING
    assert t.attempt == 0
    assert t.result is None


def test_task_graph_ordering():
    g = TaskGraph(tasks=[
        SubTask(agent="recon", objective="profile site"),
        SubTask(agent="browser", objective="fetch", depends_on=["recon"]),
    ])
    ordered = g.ready_tasks()
    assert len(ordered) == 1
    assert ordered[0].agent == "recon"


def test_subtask_advance():
    t = SubTask(agent="recon", objective="profile")
    t.mark_running()
    assert t.status == TaskStatus.RUNNING
    assert t.attempt == 1


from axelo.core.models.agent_result import AgentResult, ResultStatus


def test_agent_result_success():
    r = AgentResult(
        agent="recon",
        status=ResultStatus.SUCCESS,
        data={"antibot": "cloudflare"},
    )
    assert r.ok is True
    assert r.data["antibot"] == "cloudflare"


def test_agent_result_failure():
    r = AgentResult(agent="browser", status=ResultStatus.FAILURE, error="timeout")
    assert r.ok is False
    assert r.data == {}


from axelo.core.models.session import SessionState, SessionStatus


def test_session_state_initial():
    s = SessionState(session_id="session_000001", target_url="https://example.com", objective="get token")
    assert s.status == SessionStatus.INIT
    assert s.session_id == "session_000001"


def test_session_state_transition():
    s = SessionState(session_id="session_000001", target_url="https://x.com", objective="x")
    s.transition(SessionStatus.PLANNING)
    assert s.status == SessionStatus.PLANNING
    assert len(s.history) == 1
    assert s.history[0]["to"] == "planning"


import asyncio
from axelo.core.base_agent import BaseAgent
from axelo.core.models import SubTask, AgentResult, ResultStatus


class DummyAgent(BaseAgent):
    name = "dummy"

    async def execute(self, task: SubTask) -> AgentResult:
        return AgentResult(agent=self.name, status=ResultStatus.SUCCESS, data={"done": True})


def test_base_agent_run():
    agent = DummyAgent()
    task = SubTask(agent="dummy", objective="test")
    result = asyncio.run(agent.run(task))
    assert result.ok
    assert result.agent == "dummy"
    assert task.status.value == "complete"
