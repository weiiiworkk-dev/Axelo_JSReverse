from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.verification.agent import VerificationAgent
from axelo.core.models import SubTask, ResultStatus


def test_verification_agent_name():
    assert VerificationAgent.name == "verification"


def test_verification_pass():
    agent = VerificationAgent()
    task = SubTask(agent="verification", objective="Verify signature code")
    task.meta["code"] = "def sign(t): return t"

    with patch.object(agent, "_run_verification", new_callable=AsyncMock) as mock_v:
        mock_v.return_value = {"passed": True, "score": 1.0}
        result = asyncio.run(agent.run(task))

    assert result.ok
    assert result.data["passed"] is True


def test_verification_fail():
    agent = VerificationAgent()
    task = SubTask(agent="verification", objective="Verify signature code")
    task.meta["code"] = "def sign(t): return 'wrong'"

    with patch.object(agent, "_run_verification", new_callable=AsyncMock) as mock_v:
        mock_v.return_value = {"passed": False, "error": "hash_mismatch"}
        result = asyncio.run(agent.run(task))

    assert result.status == ResultStatus.FAILURE
