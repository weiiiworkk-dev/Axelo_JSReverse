from __future__ import annotations

from dataclasses import dataclass

from axelo.cost.governor import CostGovernor
from axelo.models.execution import ExecutionPlan, ExecutionTier, VerificationMode
from axelo.models.target import TargetSite
from axelo.storage.adapter_registry import AdapterRecord, AdapterRegistry


@dataclass
class PlanDecision:
    plan: ExecutionPlan
    adapter: AdapterRecord | None = None


class Planner:
    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def build(
        self,
        target: TargetSite,
        *,
        budget_usd: float,
        memory_ctx: dict | None = None,
    ) -> PlanDecision:
        memory_ctx = memory_ctx or {}
        governor = CostGovernor(max_usd=budget_usd)
        adapter = self._registry.lookup(target)

        reasons: list[str] = []
        plan = ExecutionPlan()

        if target.site_profile.difficulty_hint == "extreme" and target.compliance.require_manual_for_extreme:
            plan.tier = ExecutionTier.MANUAL_REVIEW
            plan.verification_mode = VerificationMode.NONE
            reasons.append("Site profile already marks the target as extreme.")
        elif adapter:
            plan.tier = ExecutionTier.ADAPTER_REUSE
            plan.adapter_hit = True
            plan.adapter_key = adapter.registry_key
            reasons.append("Verified adapter registry entry matched this target.")
        else:
            plan.tier = ExecutionTier.BROWSER_FULL
            reasons.append("No reusable adapter was found; full analysis path selected.")

            if target.known_endpoint and not target.site_profile.action_flow and not target.requires_login:
                plan.tier = ExecutionTier.BROWSER_LIGHT
                plan.requires_dynamic_analysis = False
                plan.verification_mode = VerificationMode.BASIC
                reasons.append("Known endpoint allows a lighter browser discovery pass.")

            if target.requires_login or target.site_profile.action_flow:
                plan.tier = ExecutionTier.BROWSER_FULL
                plan.requires_dynamic_analysis = True
                plan.enable_action_flow = True
                plan.enable_trace_capture = True
                plan.verification_mode = VerificationMode.STRICT if target.requires_login else VerificationMode.STANDARD
                reasons.append("Login or scripted interaction requires the full browser tier.")

            if memory_ctx.get("known_pattern") and plan.tier != ExecutionTier.BROWSER_FULL:
                plan.requires_dynamic_analysis = False
                reasons.append("Historical pattern match reduces the need for deeper analysis.")

        plan.reasons = reasons
        plan = governor.tune_plan(plan, target)
        if governor.degradation_notes:
            plan.degradation_notes.extend(governor.degradation_notes)
        return PlanDecision(plan=plan, adapter=adapter)
