from __future__ import annotations

from axelo.domain.services import PlanningService
from axelo.models.target import TargetSite
from axelo.storage.adapter_registry import AdapterRegistry


def test_planning_service_accepts_registry_and_exposes_build(tmp_path):
    service = PlanningService(AdapterRegistry(tmp_path))
    target = TargetSite(
        url="https://example.com/search?q=phone",
        session_id="plan01",
        interaction_goal="collect products",
        authorization_status="authorized",
        replay_mode="authorized_replay",
    )

    decision = service.build(target, budget_usd=1.0)

    assert decision.plan is not None
    assert decision.plan.route_label
