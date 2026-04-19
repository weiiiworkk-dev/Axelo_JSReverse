from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.codegen.agent import CodegenAgent
from axelo.core.models import SubTask, ResultStatus


def test_codegen_agent_name():
    assert CodegenAgent.name == "codegen"


def test_codegen_returns_python_code():
    agent = CodegenAgent()
    task = SubTask(agent="codegen", objective="Generate signature from candidates")
    task.meta["candidates"] = ["sign"]
    task.meta["crypto_primitives"] = ["md5"]

    with patch.object(agent, "_generate_code", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "def sign(t):\n    return hashlib.md5(t).hexdigest()"
        result = asyncio.run(agent.run(task))

    assert result.ok
    assert "def sign" in result.data.get("code", "")
