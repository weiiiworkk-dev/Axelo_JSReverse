from __future__ import annotations

from axelo.planner import PlanDecision, Planner


class PlanningService:
    """Thin application-facing wrapper around the planner."""

    def __init__(self, planner: Planner) -> None:
        self._planner = planner

    def build_plan(self, target, *, budget_usd: float, memory_ctx: dict | None = None) -> PlanDecision:
        return self._planner.build(target, budget_usd=budget_usd, memory_ctx=memory_ctx or {})
