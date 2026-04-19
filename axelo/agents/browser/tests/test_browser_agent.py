from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.browser.agent import BrowserAgent
from axelo.core.models import SubTask, ResultStatus


def test_browser_agent_name():
    assert BrowserAgent.name == "browser"


def test_browser_agent_fails_gracefully():
    agent = BrowserAgent()
    task = SubTask(agent="browser", objective="Fetch JS from https://example.com")
    with patch.object(agent, "_capture_bundles", new_callable=AsyncMock) as mock_cap:
        mock_cap.side_effect = RuntimeError("browser_unavailable")
        result = asyncio.run(agent.run(task))
    assert result.status == ResultStatus.FAILURE
    assert "browser_unavailable" in result.error
