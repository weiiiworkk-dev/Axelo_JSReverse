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
        allow_executable_replay = (
            target.authorization_status == "authorized" and target.replay_mode == "authorized_replay"
        )
        adapter = self._registry.lookup(target) if allow_executable_replay else None

        reasons: list[str] = []
        plan = ExecutionPlan()

        if target.replay_mode != "authorized_replay":
            plan.skip_codegen = True
            plan.verification_mode = VerificationMode.NONE
            plan.should_persist_adapter = False
            plan.enable_action_flow = False
            plan.enable_trace_capture = False
            plan.requires_dynamic_analysis = False
            plan.ai_mode = "scanner_only"
            plan.route_label = "scanner_only"
            plan.estimated_cost = "low"
            plan.estimated_cost_range = "$0.02-$0.10"
            reasons.append(f"Replay mode '{target.replay_mode}' disables codegen and live verification.")

        if target.authorization_status != "authorized":
            plan.skip_codegen = True
            plan.verification_mode = VerificationMode.NONE
            plan.should_persist_adapter = False
            plan.enable_action_flow = False
            plan.enable_trace_capture = False
            plan.requires_dynamic_analysis = False
            plan.ai_mode = "scanner_only"
            plan.route_label = "scanner_only"
            plan.estimated_cost = "low"
            plan.estimated_cost_range = "$0.02-$0.10"
            reasons.append(f"Authorization status '{target.authorization_status}' disables executable replay.")

        if target.site_profile.difficulty_hint == "extreme" and target.compliance.require_manual_for_extreme:
            plan.tier = ExecutionTier.MANUAL_REVIEW
            plan.verification_mode = VerificationMode.NONE
            plan.route_label = "manual_review"
            reasons.append("Site profile already marks the target as extreme.")
        elif adapter:
            plan.tier = ExecutionTier.ADAPTER_REUSE
            plan.adapter_hit = True
            plan.adapter_key = adapter.registry_key
            plan.route_label = "adapter_reuse"
            reasons.append("Verified adapter registry entry matched this target.")
        else:
            plan.tier = ExecutionTier.BROWSER_FULL
            # Default to the full route unless later conditions narrow it.
            plan.route_label = "full_ai_unknown_family"
            reasons.append("No reusable adapter was found; full analysis path selected.")

            if (
                target.known_endpoint
                and target.target_hint
                and target.requires_login is False
                and not target.site_profile.action_flow
            ):
                plan.tier = ExecutionTier.BROWSER_LIGHT
                plan.requires_dynamic_analysis = False
                plan.route_label = "scanner_only" if plan.skip_codegen else "full_ai_unknown_family"
                if plan.verification_mode != VerificationMode.NONE:
                    plan.verification_mode = VerificationMode.BASIC
                reasons.append("Known endpoint plus target hint allows a lighter browser discovery pass.")
            elif target.known_endpoint and not target.site_profile.action_flow and not target.requires_login:
                plan.tier = ExecutionTier.BROWSER_LIGHT
                plan.requires_dynamic_analysis = False
                if plan.verification_mode != VerificationMode.NONE:
                    plan.verification_mode = VerificationMode.BASIC
                reasons.append("Known endpoint allows a lighter browser discovery pass.")

            if target.requires_login or target.site_profile.action_flow:
                plan.tier = ExecutionTier.BROWSER_FULL
                plan.requires_dynamic_analysis = True
                if target.authorization_status == "authorized" and target.replay_mode == "authorized_replay":
                    plan.enable_action_flow = True
                plan.enable_trace_capture = True
                if plan.verification_mode != VerificationMode.NONE:
                    plan.verification_mode = VerificationMode.STRICT if target.requires_login else VerificationMode.STANDARD
                reasons.append("Login or scripted interaction requires the full browser tier.")

            if memory_ctx.get("known_pattern") and plan.tier != ExecutionTier.BROWSER_FULL:
                plan.requires_dynamic_analysis = False
                reasons.append("Historical pattern match reduces the need for deeper analysis.")

            if not plan.skip_codegen and plan.tier == ExecutionTier.BROWSER_FULL:
                plan.route_label = "full_ai_unknown_family"
                plan.estimated_cost_range = "$0.40-$0.90"
            elif plan.skip_codegen:
                plan.route_label = "scanner_only"
                plan.estimated_cost_range = "$0.02-$0.10"

        plan.reasons = reasons
        plan = governor.tune_plan(plan, target)
        if governor.degradation_notes:
            plan.degradation_notes.extend(governor.degradation_notes)
        return PlanDecision(plan=plan, adapter=adapter)
