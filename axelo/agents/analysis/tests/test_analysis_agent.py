from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch
from axelo.agents.analysis.agent import AnalysisAgent
from axelo.core.models import SubTask, ResultStatus


def test_analysis_agent_name():
    assert AnalysisAgent.name == "analysis"


def test_analysis_returns_candidates():
    agent = AnalysisAgent()
    task = SubTask(agent="analysis", objective="Analyze JS from browser result")
    task.meta["bundles"] = ["function sign(t){return md5(t);}"]

    with patch.object(agent, "_run_static", new_callable=AsyncMock) as mock_s, \
         patch.object(agent, "_run_dynamic", new_callable=AsyncMock) as mock_d:
        mock_s.return_value = {"candidates": ["sign"]}
        mock_d.return_value = {"traces": []}
        result = asyncio.run(agent.run(task))

    assert result.ok
    assert "candidates" in result.data
