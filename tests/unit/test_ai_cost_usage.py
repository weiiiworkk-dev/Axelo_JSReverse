from __future__ import annotations

import pytest

from axelo.agents.scanner import ScanReport, ScannerAgent
from axelo.ai.client import AIResponse
from axelo.cost import CostBudget, CostRecord
from axelo.models.analysis import StaticAnalysis
from axelo.models.target import TargetSite


class _DummyAIClient:
    def __init__(self) -> None:
        self._model = "claude-haiku-4-5"

    async def analyze(self, **kwargs):
        return AIResponse(
            data=ScanReport(
                bundle_complexity="moderate",
                detected_frameworks=["webpack"],
                crypto_libs=["hmac"],
                interesting_functions=["bundle:sign"],
                token_field_hints=["X-Sign"],
                priority_bundles=["bundle"],
                quick_verdict="ok",
                estimated_difficulty="medium",
            ),
            model="claude-haiku-4-5",
            input_tokens=11,
            output_tokens=7,
            response_id="resp_test",
        )


@pytest.mark.asyncio
async def test_scanner_agent_uses_reported_usage_for_cost():
    cost = CostRecord(session_id="cost01")
    agent = ScannerAgent(_DummyAIClient(), cost, CostBudget(max_usd=1.0), retriever=None)

    result = await agent.scan(
        TargetSite(url="https://example.com", session_id="cost01", interaction_goal="demo"),
        {"bundle": StaticAnalysis(bundle_id="bundle")},
    )

    assert result.estimated_difficulty == "medium"
    assert cost.input_tokens == 11
    assert cost.output_tokens == 7
    assert cost.total_tokens == 18
    assert cost.ai_calls == 1
