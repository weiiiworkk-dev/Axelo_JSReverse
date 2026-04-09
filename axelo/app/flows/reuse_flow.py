from __future__ import annotations

from pathlib import Path

from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.models.contracts import AdapterPackage, CapabilityProfile, DatasetContract, RequestContract
from axelo.models.execution import ExecutionPlan, ExecutionTier, VerificationMode
from axelo.models.target import TargetSite
from axelo.verification.engine import VerificationEngine

from ._common import artifact_map


class ReuseFlow:
    def __init__(self, *, store, workflow_store, adapter_registry) -> None:
        self._store = store
        self._workflow_store = workflow_store
        self._adapter_registry = adapter_registry

    async def run(self, ctx) -> bool | None:
        if ctx.target.execution_plan.tier == ExecutionTier.MANUAL_REVIEW:
            ctx.cost.set_route("manual_review")
            ctx.analysis = AnalysisResult(session_id=ctx.sid, manual_review_required=True)
            ctx.state.workflow_status = "waiting_manual_review"
            ctx.state.manual_review_reason = "; ".join(ctx.target.execution_plan.reasons)
            self._store.save(ctx.state)
            ctx.target.trace = ctx.workflow.request_manual_review(
                ctx.sid,
                ctx.target.trace,
                "planning",
                summary=ctx.state.manual_review_reason or "Planner requested manual review",
            )
            ctx.result.error = "manual review required by execution plan"
            return False

        if ctx.target.execution_plan.tier != ExecutionTier.ADAPTER_REUSE or ctx.adapter_candidate is None:
            return None

        ctx.cost.set_route("adapter_reuse")
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "adapter_reuse",
            "running",
            summary=getattr(ctx.adapter_candidate, "registry_key", ""),
        )
        reused, reuse_verified = await self._reuse_adapter(
            sid=ctx.sid,
            target=ctx.target,
            adapter=ctx.adapter_candidate,
            output_dir=ctx.output_dir,
        )
        if reuse_verified:
            ctx.generated = reused
            ctx.verified = True
            ctx.result.output_dir = ctx.output_dir
            ctx.result.adapter_reused = True
            ctx.cost.add_reuse_hit("adapter")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "adapter_reuse",
                "completed",
                summary="Verified adapter reused successfully",
                artifacts=artifact_map(
                    {
                        key: path
                        for key, path in {
                            "crawler_script": reused.crawler_script_path,
                            "bridge_server": reused.bridge_server_path,
                            "manifest": reused.manifest_path,
                            "session_state": reused.session_state_path,
                        }.items()
                        if path is not None
                    }
                ),
            )
            return True

        ctx.target.execution_plan = _escalate_execution_plan(
            ctx.target.execution_plan,
            "Adapter reuse failed verification; escalating to full pipeline.",
        )
        ctx.state.execution_plan = ctx.target.execution_plan.model_dump(mode="json")
        self._store.save(ctx.state)
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "adapter_reuse",
            "failed",
            summary="Adapter verification failed, escalated to full pipeline",
        )
        return None

    async def _reuse_adapter(
        self,
        *,
        sid: str,
        target: TargetSite,
        adapter,
        output_dir: Path,
    ) -> tuple[GeneratedCode, bool]:
        materialized = self._adapter_registry.materialize(adapter, output_dir)
        if materialized.session_state_path:
            target.session_state.storage_state_path = str(materialized.session_state_path)
        if materialized.adapter_package_path and materialized.adapter_package_path.exists():
            try:
                package = AdapterPackage.model_validate_json(materialized.adapter_package_path.read_text(encoding="utf-8"))
                target.selected_contract = RequestContract.model_validate(package.request_contract)
                target.request_contracts = [target.selected_contract]
                target.dataset_contract = DatasetContract.model_validate(package.dataset_contract)
                target.capability_profile = CapabilityProfile.model_validate(package.capability_profile)
            except Exception:
                pass

        # Pre-flight: reject adapters whose stored contract is clearly mismatched
        # with the current intent's resource_kind before spending time on live
        # verification.  This is a generic heuristic — no site-specific rules.
        if target.selected_contract and target.intent:
            mismatch_reason = _contract_resource_kind_mismatch(
                target.selected_contract.url_pattern or "",
                target.intent.resource_kind or "",
            )
            if mismatch_reason:
                import structlog as _sl
                _sl.get_logger().warning(
                    "adapter_reuse_contract_mismatch",
                    url_pattern=target.selected_contract.url_pattern,
                    resource_kind=target.intent.resource_kind,
                    reason=mismatch_reason,
                )
                return (
                    GeneratedCode(
                        session_id=sid,
                        output_mode=adapter.output_mode,
                        crawler_script_path=materialized.crawler_script_path,
                        bridge_server_path=materialized.bridge_server_path,
                        manifest_path=materialized.manifest_path,
                        adapter_package_path=materialized.adapter_package_path,
                        session_state_path=materialized.session_state_path,
                        verified=False,
                        verification_notes=f"adapter contract mismatch: {mismatch_reason}",
                    ),
                    False,
                )

        generated = GeneratedCode(
            session_id=sid,
            output_mode=adapter.output_mode,
            crawler_script_path=materialized.crawler_script_path,
            bridge_server_path=materialized.bridge_server_path,
            manifest_path=materialized.manifest_path,
            adapter_package_path=materialized.adapter_package_path,
            session_state_path=materialized.session_state_path,
            verified=False,
            verification_notes="adapter registry reuse candidate",
        )

        verifier = VerificationEngine()
        verification = await verifier.verify(
            generated,
            target,
            live_verify=target.compliance.allow_live_verification,
        )
        generated.verified = verification.ok
        generated.verification_notes = verification.report
        return generated, verification.ok


def _escalate_execution_plan(plan: ExecutionPlan, reason: str) -> ExecutionPlan:
    escalated = plan.model_copy(deep=True)
    escalated.tier = ExecutionTier.BROWSER_FULL
    escalated.adapter_hit = False
    escalated.adapter_key = ""
    escalated.requires_browser = True
    escalated.requires_dynamic_analysis = True
    escalated.requires_ai = True
    escalated.skip_fetch_and_static = False
    escalated.skip_codegen = False
    escalated.should_persist_adapter = True
    escalated.enable_trace_capture = True
    escalated.enable_action_flow = True
    escalated.enable_target_confirmation = True
    escalated.max_crawl_retries = max(2, escalated.max_crawl_retries)
    escalated.max_session_rotations = max(2, escalated.max_session_rotations)
    escalated.verification_mode = VerificationMode.STANDARD
    escalated.reasons.append(reason)
    return escalated


# URL path segments that indicate autocomplete / suggestion endpoints — these
# are structurally incompatible with product_listing / search_results intents.
_SUGGESTION_PATH_TOKENS = frozenset({
    "/suggest", "/suggestions", "/autocomplete", "/typeahead",
    "/completion", "/search_suggest", "/autosuggest", "/query_suggest",
})

# Resource kinds that require actual data records, not auxiliary query helpers.
_DATA_RESOURCE_KINDS = frozenset({
    "product_listing", "search_results", "reviews", "content_listing",
})


def _contract_resource_kind_mismatch(url_pattern: str, resource_kind: str) -> str:
    """Return a non-empty reason string if the stored contract's URL pattern is
    structurally incompatible with the requested resource_kind.

    This is a pure heuristic with no site-specific logic — only URL path
    semantics are inspected.
    """
    if resource_kind not in _DATA_RESOURCE_KINDS:
        return ""
    url_lower = url_pattern.lower()
    for token in _SUGGESTION_PATH_TOKENS:
        if token in url_lower:
            return (
                f"contract URL '{url_pattern}' is a suggestion/autocomplete endpoint "
                f"but resource_kind='{resource_kind}' requires structured data records"
            )
    return ""
