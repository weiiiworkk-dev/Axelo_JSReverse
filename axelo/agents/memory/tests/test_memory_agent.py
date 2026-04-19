from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.memory.agent import MemoryAgent
from axelo.core.models import SubTask, ResultStatus


def test_memory_agent_name():
    assert MemoryAgent.name == "memory"


def test_memory_write_success():
    agent = MemoryAgent()
    task = SubTask(agent="memory", objective="Store pattern for example.com")
    task.meta["domain"] = "example.com"
    task.meta["code"] = "def sign(t): return t"
    task.meta["antibot"] = "none"

    with patch.object(agent, "_write_pattern", new_callable=AsyncMock) as mock_w:
        mock_w.return_value = {"written": True, "pattern_id": 42}
        result = asyncio.run(agent.run(task))

    assert result.ok
    assert result.data["written"] is True
