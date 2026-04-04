from __future__ import annotations

from axelo.planner import PlanDecision, Planner
from axelo.storage.adapter_registry import AdapterRegistry


class PlanningService:
    """Thin application-facing wrapper around the planner."""

    def __init__(self, planner: Planner | AdapterRegistry) -> None:
        # Keep the service backward-compatible with older call sites that still
        # pass an AdapterRegistry directly instead of a Planner instance.
        self._planner = planner if isinstance(planner, Planner) else Planner(planner)

    def build_plan(self, target, *, budget_usd: float, memory_ctx: dict | None = None) -> PlanDecision:
        return self._planner.build(target, budget_usd=budget_usd, memory_ctx=memory_ctx or {})

    def build(self, target, *, budget_usd: float, memory_ctx: dict | None = None) -> PlanDecision:
        return self.build_plan(target, budget_usd=budget_usd, memory_ctx=memory_ctx)
