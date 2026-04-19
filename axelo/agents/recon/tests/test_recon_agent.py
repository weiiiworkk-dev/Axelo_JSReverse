from __future__ import annotations
import asyncio
from unittest.mock import patch, AsyncMock
from axelo.agents.recon.agent import ReconAgent
from axelo.core.models import SubTask, ResultStatus


def test_recon_agent_name():
    assert ReconAgent.name == "recon"


def test_recon_agent_returns_site_profile():
    agent = ReconAgent()
    task = SubTask(agent="recon", objective="Profile https://example.com")
    fake_profile = {
        "url": "https://example.com",
        "antibot_system": "none",
        "js_challenge": False,
        "difficulty": "easy",
    }
    with patch.object(agent, "_profile_site", new_callable=AsyncMock) as mock_profile:
        mock_profile.return_value = fake_profile
        result = asyncio.run(agent.run(task))
    assert result.ok
    assert result.data.get("antibot_system") == "none"
    assert result.agent == "recon"
