from __future__ import annotations

from dataclasses import dataclass, field

from axelo.cost.tracker import CostRecord
from axelo.models.execution import ExecutionPlan, ExecutionTier, VerificationMode
from axelo.models.target import TargetSite


@dataclass
class CostGovernor:
    max_usd: float
    degradation_notes: list[str] = field(default_factory=list)

    def tune_plan(self, plan: ExecutionPlan, target: TargetSite) -> ExecutionPlan:
        tuned = plan.model_copy(deep=True)

        if self.max_usd <= 0.35 and tuned.tier == ExecutionTier.BROWSER_FULL and not target.requires_login:
            tuned.tier = ExecutionTier.BROWSER_LIGHT
            tuned.requires_dynamic_analysis = False
            tuned.enable_trace_capture = False
            tuned.max_crawl_retries = 1
            tuned.max_bundles = 3
            tuned.max_bundle_size_kb = 256
            tuned.max_total_bundle_kb = 700
            tuned.verification_mode = VerificationMode.BASIC
            tuned.estimated_cost_range = "$0.08-$0.25"
            tuned.degradation_notes.append("Budget pressure downgraded browser execution to light mode.")

        if self.max_usd <= 0.2:
            tuned.requires_dynamic_analysis = False
            tuned.verification_mode = VerificationMode.BASIC
            tuned.enable_trace_capture = False
            tuned.max_bundles = min(tuned.max_bundles, 2)
            tuned.max_bundle_size_kb = min(tuned.max_bundle_size_kb, 192)
            tuned.max_total_bundle_kb = min(tuned.max_total_bundle_kb, 450)
            tuned.estimated_cost_range = "$0.03-$0.12"
            tuned.degradation_notes.append("Very low budget disables trace-heavy and dynamic stages.")

        if tuned.tier == ExecutionTier.BROWSER_LIGHT:
            tuned.enable_action_flow = False
            tuned.enable_trace_capture = False
            tuned.max_session_rotations = min(tuned.max_session_rotations, 2)
            tuned.max_bundles = min(tuned.max_bundles, 3)
            tuned.max_bundle_size_kb = min(tuned.max_bundle_size_kb, 256)
            tuned.max_total_bundle_kb = min(tuned.max_total_bundle_kb, 700)
            tuned.estimated_cost = "low"
            tuned.estimated_cost_range = "$0.05-$0.20"

        if tuned.tier == ExecutionTier.ADAPTER_REUSE:
            tuned.requires_browser = False
            tuned.requires_dynamic_analysis = False
            tuned.requires_ai = False
            tuned.ai_mode = "none"
            tuned.skip_fetch_and_static = True
            tuned.skip_codegen = True
            tuned.enable_trace_capture = False
            tuned.enable_action_flow = False
            tuned.enable_target_confirmation = False
            tuned.max_crawl_retries = 1
            tuned.max_session_rotations = 1
            tuned.max_bundles = 1
            tuned.max_bundle_size_kb = 64
            tuned.max_total_bundle_kb = 64
            tuned.estimated_cost = "low"
            tuned.estimated_cost_range = "$0.00-$0.05"
            tuned.verification_mode = VerificationMode.BASIC

        if tuned.tier == ExecutionTier.MANUAL_REVIEW:
            tuned.requires_browser = False
            tuned.requires_dynamic_analysis = False
            tuned.requires_ai = False
            tuned.ai_mode = "none"
            tuned.skip_fetch_and_static = True
            tuned.skip_codegen = True
            tuned.enable_trace_capture = False
            tuned.enable_action_flow = False
            tuned.enable_target_confirmation = False
            tuned.verification_mode = VerificationMode.NONE
            tuned.should_persist_adapter = False
            tuned.max_bundles = 1
            tuned.max_bundle_size_kb = 64
            tuned.max_total_bundle_kb = 64
            tuned.estimated_cost = "minimal"
            tuned.estimated_cost_range = "$0.00-$0.02"

        return tuned

    def allow_dynamic(self, record: CostRecord, plan: ExecutionPlan) -> bool:
        if not plan.requires_dynamic_analysis:
            return False
        if record.total_usd > self.max_usd * 0.55:
            self.degradation_notes.append("Skipped dynamic analysis due to budget threshold.")
            return False
        return True

    def allow_ai(self, record: CostRecord, plan: ExecutionPlan) -> bool:
        if not plan.requires_ai:
            return False
        if record.total_usd > self.max_usd * 0.9:
            self.degradation_notes.append("Skipped AI stage because budget ceiling was reached.")
            return False
        return True

    def stability_runs(self, target: TargetSite, plan: ExecutionPlan) -> int:
        if plan.verification_mode == VerificationMode.NONE:
            return 1
        if plan.verification_mode == VerificationMode.BASIC:
            return 1
        if plan.verification_mode == VerificationMode.STRICT:
            return max(target.compliance.stability_runs, 3)
        return max(1, target.compliance.stability_runs)
