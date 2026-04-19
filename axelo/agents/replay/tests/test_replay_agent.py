from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.replay.agent import ReplayAgent
from axelo.core.models import SubTask, ResultStatus


def test_replay_agent_name():
    assert ReplayAgent.name == "replay"


def test_replay_high_success_rate():
    agent = ReplayAgent()
    task = SubTask(agent="replay", objective="Replay with generated signature")
    task.meta["code"] = "def sign(t): return t"
    task.meta["target_url"] = "https://example.com/api"

    with patch.object(agent, "_replay_requests", new_callable=AsyncMock) as mock_r:
        mock_r.return_value = {"success_rate": 0.95, "total": 10, "success": 9}
        result = asyncio.run(agent.run(task))

    assert result.ok
    assert result.data["success_rate"] >= 0.8


def test_replay_low_success_triggers_failure():
    agent = ReplayAgent()
    task = SubTask(agent="replay", objective="Replay")
    task.meta["code"] = "def sign(t): return 'bad'"
    task.meta["target_url"] = "https://example.com/api"

    with patch.object(agent, "_replay_requests", new_callable=AsyncMock) as mock_r:
        mock_r.return_value = {"success_rate": 0.3, "total": 10, "success": 3}
        result = asyncio.run(agent.run(task))

    assert result.status == ResultStatus.FAILURE
    assert result.data["success_rate"] < 0.8
