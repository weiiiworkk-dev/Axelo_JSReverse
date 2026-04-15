from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axelo.engine.models import (
    MechanismAssessment,
    MissionOutcome,
    NextActionSpec,
    PrincipalAgentState,
    VerdictChain,
    VerdictTier,
    VERDICT_RANK,
    TIER_TO_OUTCOME,
    now_iso,
)


class AgendaReconciler:
    """
    Mandatory reconciliation pass that closes open agenda items before any verdict
    is classified. Fixes the session 000006 class of bugs where mission.status=success
    was issued while agenda items were still in_progress.

    Call reconcile() AFTER the execution loop completes, BEFORE classify_outcome().
    """

    # Maps agenda item_id → coverage dimension used to auto-close it
    _ITEM_DIMENSION: dict[str, str] = {
        "mission:surface":   "acquisition",
        "mission:transport": "protocol",
        "mission:build":     "build",
        "mission:verify":    "verify",
        "mission:reverse":   "reverse",
        "mission:runtime":   "runtime",
        "mission:schema":    "schema",
    }

    @classmethod
    def reconcile(cls, state: PrincipalAgentState, coverage: dict[str, float]) -> list[str]:
        """
        Mutates state.agenda in-place to ensure all items are in terminal state.
        Returns list of reconciliation action strings (for audit log and VerdictChain).
        """
        actions: list[str] = []
        for item in state.agenda:
            if item.status not in ("in_progress", "pending"):
                continue  # already in terminal state

            # Rule 1: mechanism not required → transport/reverse/runtime are not applicable
            if not state.mission.mechanism_required and item.item_id in (
                "mission:transport", "mission:reverse", "mission:runtime"
            ):
                item.status = "not_applicable"
                item.rationale = "Not applicable: mechanism_required=False for this mission type"
                item.updated_at = now_iso()
                actions.append(f"NOT_APPLICABLE: {item.item_id} (mechanism not required)")
                continue

            # Rule 2: If the corresponding coverage dimension reached ≥ 0.7, auto-close as completed
            dim = cls._ITEM_DIMENSION.get(item.item_id)
            if dim and coverage.get(dim, 0.0) >= 0.7:
                item.status = "completed"
                item.rationale = (
                    f"Auto-closed: {dim} coverage={coverage[dim]:.2f} ≥ 0.70"
                )
                item.updated_at = now_iso()
                actions.append(f"AUTO_COMPLETE: {item.item_id} (coverage {dim}={coverage[dim]:.2f})")
                continue

            # Rule 3: If the objective stalled ≥ 2 times with no progress, auto-fail
            stalls = (state.objective_stalls or {}).get(item.label, 0)
            # Also check by common objective names
            for obj_key, stall_count in (state.objective_stalls or {}).items():
                if item.item_id.replace("mission:", "") in obj_key:
                    stalls = max(stalls, stall_count)
            if stalls >= 2:
                item.status = "failed"
                item.rationale = f"Auto-failed: objective stalled {stalls} times with no evidence gain"
                item.updated_at = now_iso()
                actions.append(f"AUTO_FAIL: {item.item_id} (stalls={stalls})")
                continue

        # After reconciliation, check if any items are still open
        still_open = [item.item_id for item in state.agenda if item.status in ("in_progress", "pending")]
        if still_open:
            # Force-close remaining open items as "inconclusive" — prevents verdict deadlock
            for item in state.agenda:
                if item.status in ("in_progress", "pending"):
                    item.status = "inconclusive"
                    item.rationale = "Force-closed: mission complete but item had insufficient evidence"
                    item.updated_at = now_iso()
                    actions.append(f"FORCE_INCONCLUSIVE: {item.item_id}")
            state.mission.has_unresolved_agenda = True
            actions.append(f"UNRESOLVED_AGENDA: {still_open} → verdict will be capped at PARTIAL_SUCCESS")
        else:
            state.mission.has_unresolved_agenda = False

        if actions:
            state.worklog.append(f"Agenda reconciled before verdict: {len(actions)} action(s)")
            state.worklog.extend(actions)

        return actions

    @classmethod
    def all_closed(cls, state: PrincipalAgentState) -> bool:
        """True only if no agenda item is still in_progress or pending."""
        return not any(item.status in ("in_progress", "pending") for item in state.agenda)


@dataclass
class ConstitutionalSignals:
    acquisition: float
    protocol: float
    reverse: float
    runtime: float
    schema: float
    extraction: float
    build: float
    verify: float
    execution_trust: float
    mechanism_trust: float
    open_questions: int
    blockers: list[str]


class EngineConstitution:
    principles = (
        "Mission progress is driven by evidence gaps, not by a preset tool order.",
        "Operational success and mechanism truth are distinct and must be scored separately.",
        "New work should reduce the dominant uncertainty instead of merely adding more output.",
        "Build only when the extraction path is grounded enough to justify code generation.",
        "Verification can confirm delivery, but it cannot silently stand in for mechanism evidence.",
    )

    @staticmethod
    def infer_mechanism_required(
        objective: str | None,
        *,
        intent_type: str = "",
        explicit: bool | None = None,
    ) -> bool:
        if explicit is not None:
            return bool(explicit)
        if intent_type.strip().lower() in {"reverse", "reverse_engineer", "analyze_protocol"}:
            return True
        text = str(objective or "").strip().lower()
        if not text:
            return True
        tokens = (
            "reverse",
            "signature",
            "signing",
            "token",
            "fingerprint",
            "anti-bot",
            "runtime",
            "mechanism",
            "protocol",
            "replay or",
            "deeper mechanism",
            "逆向",
            "签名",
            "协议",
        )
        return any(token in text for token in tokens)

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def evidence_coverage(cls, state: PrincipalAgentState | None) -> dict[str, float]:
        coverage = {
            "acquisition": 0.0,
            "protocol": 0.0,
            "reverse": 0.0,
            "runtime": 0.0,
            "schema": 0.0,
            "extraction": 0.0,
            "build": 0.0,
            "verify": 0.0,
        }
        if state is None:
            return coverage
        for record in state.evidence:
            value = max(cls._as_float(record.confidence), 0.2)
            details = record.details or {}
            if record.kind in {"browser", "fetch", "fetch_js_bundles", "surface"}:
                if details.get("page_title") or details.get("bundle_count") or details.get("js_bundles"):
                    value = max(value, 0.6)
                coverage["acquisition"] = max(coverage["acquisition"], value)
            elif record.kind in {"protocol", "transport"}:
                if details.get("request_fields") or details.get("required_headers") or details.get("target_request_url"):
                    value = max(value, 0.7)
                coverage["protocol"] = max(coverage["protocol"], value)
            elif record.kind in {"static", "reverse"}:
                strong_static = bool(details.get("algorithms") or details.get("signature_spec") or details.get("token_candidates"))
                weak_static = bool(details.get("signature_candidates") or details.get("api_endpoints"))
                if strong_static:
                    value = max(value, 0.65)
                elif weak_static:
                    value = min(value, 0.35)
                else:
                    value = min(value, 0.25)
                coverage["reverse"] = max(coverage["reverse"], value)
            elif record.kind == "signature_extractor":
                extracted_confidence = cls._as_float(details.get("confidence"), 0.0)
                if extracted_confidence > 0.0:
                    value = max(extracted_confidence, 0.45 if details.get("algorithm") else 0.25)
                else:
                    value = 0.15
                coverage["reverse"] = max(coverage["reverse"], value)
            elif record.kind == "ai_analyze":
                signature_extraction = details.get("signature_extraction") or {}
                supporting_confidence = cls._as_float(signature_extraction.get("confidence"), 0.0)
                if details.get("signature_type") and supporting_confidence >= 0.45:
                    value = max(min(value, 0.6), 0.45)
                else:
                    value = min(value, 0.25)
                coverage["reverse"] = max(coverage["reverse"], value)
            elif record.kind in {"runtime_hook", "runtime"}:
                if details.get("runtime_sensitive_fields") or details.get("hook_points"):
                    value = max(value, 0.7)
                coverage["runtime"] = max(coverage["runtime"], value)
            elif record.kind in {"response_schema", "schema"}:
                if details.get("listing_item_fields") or details.get("schema_fields"):
                    value = max(value, 0.7)
                coverage["schema"] = max(coverage["schema"], value)
            elif record.kind in {"extraction"}:
                value = max(value, cls._as_float(details.get("coverage"), value))
                coverage["extraction"] = max(coverage["extraction"], value)
            elif record.kind in {"codegen", "build"}:
                if details.get("python_code") or details.get("crawler_path") or details.get("manifest"):
                    value = max(value, 0.75)
                coverage["build"] = max(coverage["build"], value)
            elif record.kind in {"verify"}:
                # Three-layer verify scoring:
                # Layer 1 (40%): execution — did the code run?
                exec_verdict = str(details.get("execution_verdict") or details.get("success") or "").lower()
                exec_ok = exec_verdict in {"pass", "true"}
                if not exec_ok:
                    score = 0.15
                else:
                    layer1 = 0.85
                    # Layer 2 (35%): structural — are fields present, do counts match?
                    struct_v = str(details.get("structural_verdict") or "").lower()
                    layer2 = 0.70 if struct_v == "pass" else 0.40 if struct_v == "partial" else 0.10
                    # Layer 3 (25%): semantic — do field values make sense?
                    sem_v = str(details.get("semantic_verdict") or "").lower()
                    layer3 = 0.90 if sem_v == "validated" else 0.55 if sem_v == "suspicious" else 0.20
                    score = layer1 * 0.40 + layer2 * 0.35 + layer3 * 0.25
                    # Cap: page_extract fallback without mechanism closure cannot exceed 0.65
                    fallback = str(details.get("fallback_strategy") or "").lower()
                    mechanism_closure = bool(details.get("mechanism_closure", False))
                    if fallback == "page_extract" and not mechanism_closure:
                        score = min(score, 0.65)
                coverage["verify"] = max(coverage["verify"], round(min(score, 1.0), 3))
        return {name: min(max(value, 0.0), 1.0) for name, value in coverage.items()}

    @classmethod
    def execution_trust(cls, state: PrincipalAgentState | None) -> dict[str, Any]:
        coverage = cls.evidence_coverage(state)
        score = (
            coverage["verify"] * 0.45
            + coverage["build"] * 0.2
            + coverage["extraction"] * 0.2
            + coverage["schema"] * 0.15
        )
        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
        return {
            "score": min(score, 1.0),
            "level": level,
            "summary": (
                f"Execution trust is {level} ({score:.2f}) based on verify={coverage['verify']:.2f}, "
                f"build={coverage['build']:.2f}, extraction={coverage['extraction']:.2f}."
            ),
        }

    @classmethod
    def mechanism_assessment(cls, state: PrincipalAgentState | None) -> MechanismAssessment:
        if state is None:
            return MechanismAssessment(summary="No mission state available.")
        coverage = cls.evidence_coverage(state)
        blockers: list[str] = []
        non_blocking_gaps: list[str] = []
        explained = {
            "surface": coverage["acquisition"] >= 0.55,
            "transport": coverage["protocol"] >= 0.55,
            "reverse": coverage["reverse"] >= 0.55,
            "runtime": coverage["runtime"] >= 0.55 or not state.mission.mechanism_required,
            "schema": coverage["schema"] >= 0.55,
        }
        if not explained["surface"]:
            blockers.append("Primary surface is still weakly grounded.")
        # Transport clarity is only a hard blocker when mechanism claims are being made.
        # For pure extraction/scraping missions (mechanism_required=False), protocol
        # coverage below 0.55 is tracked but does not prevent operational success.
        if not explained["transport"] and state.mission.mechanism_required:
            blockers.append("Transport-sensitive fields or headers remain unclear.")
        if state.mission.mechanism_required and not explained["reverse"]:
            blockers.append("Static or signature evidence is insufficient for mechanism claims.")
        if state.mission.mechanism_required and not explained["runtime"]:
            blockers.append("Runtime-sensitive evidence is insufficient for mechanism closure.")
        if not explained["schema"]:
            non_blocking_gaps.append("Schema evidence is still incomplete.")
        dominant = ""
        if state.hypotheses:
            leader = max(state.hypotheses, key=lambda item: item.posterior)
            dominant = leader.hypothesis_id
            if leader.posterior < 0.55 and state.mission.mechanism_required:
                blockers.append("No dominant hypothesis has separated from alternatives.")
        verdict = "validated"
        if blockers:
            verdict = "replay_only" if coverage["verify"] >= 0.7 else "unknown"
        elif coverage["reverse"] < 0.75 or coverage["protocol"] < 0.75:
            verdict = "partial"
        return MechanismAssessment(
            verdict=verdict,
            summary=f"Mechanism assessment is {verdict} with {len(blockers)} blockers.",
            dominant_hypothesis_id=dominant,
            blocking_conditions=blockers,
            non_blocking_gaps=non_blocking_gaps,
            explained_dimensions=explained,
            unresolved_dimensions=[name for name, ok in explained.items() if not ok],
        )

    @classmethod
    def mechanism_trust(cls, state: PrincipalAgentState | None) -> dict[str, Any]:
        coverage = cls.evidence_coverage(state)
        assessment = cls.mechanism_assessment(state)
        penalty = min(len(assessment.blocking_conditions) * 0.08, 0.4)
        score = (
            coverage["acquisition"] * 0.15
            + coverage["protocol"] * 0.25
            + coverage["reverse"] * 0.3
            + coverage["runtime"] * 0.2
            + coverage["verify"] * 0.1
        ) - penalty
        score = min(max(score, 0.0), 1.0)
        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
        return {
            "score": score,
            "level": level,
            "summary": (
                f"Mechanism trust is {level} ({score:.2f}) with protocol={coverage['protocol']:.2f}, "
                f"reverse={coverage['reverse']:.2f}, runtime={coverage['runtime']:.2f}."
            ),
        }

    @classmethod
    def trust_score(cls, state: PrincipalAgentState | None) -> dict[str, Any]:
        execution = cls.execution_trust(state)
        mechanism = cls.mechanism_trust(state)
        requires_mechanism = bool(state and state.mission.mechanism_required)
        score = min(execution["score"], mechanism["score"]) if requires_mechanism else execution["score"]
        level = "high" if score >= 0.8 else "medium" if score >= 0.5 else "low"
        return {
            "score": score,
            "level": level,
            "summary": f"Overall trust is {level} ({score:.2f}).",
            "execution": execution,
            "mechanism": mechanism,
            "indicators": {
                "execution": execution["score"],
                "mechanism": mechanism["score"],
            },
        }

    @classmethod
    def signals(cls, state: PrincipalAgentState | None) -> ConstitutionalSignals:
        coverage = cls.evidence_coverage(state)
        trust = cls.trust_score(state)
        assessment = cls.mechanism_assessment(state)
        return ConstitutionalSignals(
            acquisition=coverage["acquisition"],
            protocol=coverage["protocol"],
            reverse=coverage["reverse"],
            runtime=coverage["runtime"],
            schema=coverage["schema"],
            extraction=coverage["extraction"],
            build=coverage["build"],
            verify=coverage["verify"],
            execution_trust=trust["execution"]["score"],
            mechanism_trust=trust["mechanism"]["score"],
            open_questions=len(state.open_questions) if state else 0,
            blockers=list(assessment.blocking_conditions),
        )

    @classmethod
    def branch_score(cls, state: PrincipalAgentState | None, branch: Any) -> float:
        base = cls.trust_score(state)["score"]
        spent = cls._as_float(getattr(branch, "spent_budget", 0.0))
        weight = cls._as_float(getattr(branch, "budget_weight", 1.0), 1.0)
        return min(max(base + weight * 0.2 - spent * 0.15, 0.0), 1.0)

    @classmethod
    def recommend_next_action(cls, state: PrincipalAgentState) -> NextActionSpec:
        coverage = cls.evidence_coverage(state)
        assessment = cls.mechanism_assessment(state)
        stalled_schema = int((state.objective_stalls or {}).get("recover_response_schema", 0))
        stalled_build = int((state.objective_stalls or {}).get("build_artifacts", 0))
        stalled_static = int((state.objective_stalls or {}).get("recover_static_mechanism", 0))
        stalled_runtime = int((state.objective_stalls or {}).get("recover_runtime_mechanism", 0))

        if coverage["acquisition"] < 0.55:
            return NextActionSpec(
                objective_id="objective:surface",
                objective="discover_surface",
                capability="recon",
                reason="The principal surface is not grounded yet.",
                needed_evidence=["page capture", "bundle references", "observed requests"],
            )
        # Transport recovery is only mandatory when mechanism claims are being made.
        # For pure extraction/scraping missions, skip directly to schema/build/verify.
        if coverage["protocol"] < 0.55 and state.mission.mechanism_required:
            return NextActionSpec(
                objective_id="objective:transport",
                objective="recover_transport",
                capability="transport",
                reason="Transport-sensitive fields are still under-specified.",
                needed_evidence=["request fields", "headers", "cookies"],
            )
        # Mechanism recovery: static and runtime. After stalls, degrade gracefully to
        # page-extract mode (schema→build→verify) rather than halting the mission.
        # This is a capability degradation, not a failure: the system delivers what it can
        # (page-extracted data) while reporting that mechanism closure was not achieved.
        if state.mission.mechanism_required and coverage["reverse"] < 0.55:
            # Only attempt static if it hasn't stalled yet (one genuine attempt allowed).
            # After the first stall, escalate to runtime rather than retrying static.
            if stalled_static == 0:
                return NextActionSpec(
                    objective_id="objective:reverse",
                    objective="recover_static_mechanism",
                    capability="reverse",
                    reason="Mechanism claims lack static or signature evidence.",
                    needed_evidence=["static candidates", "signature inputs", "algorithm hints"],
                )
            # Static stalled — escalate to runtime hook analysis before giving up.
            # Fall through if runtime has also stalled.
        if state.mission.mechanism_required and coverage["runtime"] < 0.55:
            # Attempt runtime if static stalled OR as the normal next step.
            # After the first runtime stall, fall through to schema/build (page-extract mode).
            if stalled_runtime == 0:
                return NextActionSpec(
                    objective_id="objective:runtime",
                    objective="recover_runtime_mechanism",
                    capability="runtime",
                    reason="Runtime-sensitive evidence is still missing.",
                    needed_evidence=["hook points", "runtime fields", "fingerprint sources"],
                )
            # Both static and runtime stalled. Fall through to schema/build/verify using
            # whatever surface + transport evidence we have. This produces a PARTIAL_SUCCESS
            # verdict (mechanism unproven) rather than a hard FAILED. Page-extract mode.
        if coverage["schema"] < 0.55:
            if stalled_schema >= 1:
                # If surface evidence is solid, bypass stalled schema recovery and attempt
                # artifact generation directly using whatever DOM/HTML evidence is available.
                # This prevents the system from looping in challenge_findings when the target
                # serves HTML listings that have no embedded JSON schema.
                # For non-mechanism missions, protocol clarity is not required for this bypass.
                protocol_ok = coverage["protocol"] >= 0.55 or not state.mission.mechanism_required
                if coverage["acquisition"] >= 0.65 and protocol_ok:
                    # Only bypass to build if artifacts have not already been attempted.
                    # If extraction/build coverage is already ≥ 0.55, build is done — fall
                    # through so verify_execution gets recommended instead of looping here.
                    if coverage["extraction"] < 0.55 or coverage["build"] < 0.55:
                        return NextActionSpec(
                            objective_id="objective:build",
                            objective="build_artifacts",
                            capability="builder",
                            reason="Schema recovery stalled; acquisition evidence is sufficient to generate extraction artifacts from available HTML/DOM evidence.",
                            needed_evidence=["dom selectors", "mapped fields", "generated crawler manifest"],
                        )
                return NextActionSpec(
                    objective_id="objective:critic",
                    objective="challenge_findings",
                    capability="critic",
                    reason="Schema recovery is stalled and needs a critical review before further retries.",
                    needed_evidence=["schema gaps", "extraction blockers", "scope decision"],
                )
            return NextActionSpec(
                objective_id="objective:schema",
                objective="recover_response_schema",
                capability="schema",
                reason="Extraction should not proceed without a grounded response or DOM schema.",
                needed_evidence=["listing fields", "schema paths", "pagination signals"],
            )
        if coverage["extraction"] < 0.55 or coverage["build"] < 0.55:
            if stalled_build >= 2:
                return NextActionSpec(
                    objective_id="objective:critic",
                    objective="challenge_findings",
                    capability="critic",
                    reason="Build preparation is stalled and needs a review of the mission evidence.",
                    needed_evidence=["mapped fields", "build blockers", "verification fallback"],
                )
            return NextActionSpec(
                objective_id="objective:build",
                objective="build_artifacts",
                capability="builder",
                reason="The mission has enough grounding to build extraction and crawler artifacts.",
                needed_evidence=["mapped fields", "generated crawler manifest"],
            )
        if coverage["verify"] < 0.8:
            return NextActionSpec(
                objective_id="objective:verify",
                objective="verify_execution",
                capability="verifier",
                reason="Delivery claims still need direct verification evidence.",
                needed_evidence=["verification verdict", "retry or blocker analysis"],
            )
        if assessment.blocking_conditions:
            return NextActionSpec(
                objective_id="objective:critic",
                objective="challenge_findings",
                capability="critic",
                reason="Verification succeeded but mechanism blockers remain.",
                needed_evidence=list(assessment.blocking_conditions),
            )
        return NextActionSpec(
            objective_id="objective:produce",
            objective="produce_final",
            capability="produce",
            reason="The mission has sufficient evidence to finalize.",
            needed_evidence=[],
        )

    @classmethod
    def classify_outcome(
        cls,
        state: PrincipalAgentState | None,
        execution_success: bool,
        contract: Any | None = None,
    ) -> dict[str, Any]:
        """
        Classify mission outcome using the new VerdictTier model.
        Returns a dict with: status, outcome (legacy), verdict_tier, summary, verdict_chain.
        MUST be called after AgendaReconciler.reconcile() has run.
        """
        if state is None:
            chain = VerdictChain(
                tier=VerdictTier.FAILED,
                status="failed",
                conditions_failed=["Mission state was unavailable"],
                assessed_at=now_iso(),
            )
            return {
                "status": "failed",
                "outcome": MissionOutcome.FAILED.value,
                "verdict_tier": VerdictTier.FAILED.value,
                "summary": "Mission state was unavailable.",
                "verdict_chain": chain,
            }

        coverage = cls.evidence_coverage(state)
        assessment = cls.mechanism_assessment(state)
        conditions_met: list[str] = []
        conditions_failed: list[str] = []
        evidence_refs: list[str] = [e.evidence_id for e in state.evidence[-10:]]  # last 10 for audit

        # Collect field evidence from contract if present
        field_verdict: dict[str, str] = {}
        field_evidence = []
        if contract is not None:
            field_evidence = getattr(contract, "field_evidence", [])
            field_verdict = {fe.field_name: fe.validation_status for fe in field_evidence}
            must_have = getattr(contract, "must_have_fields", lambda: [])()
        else:
            must_have = []

        # --- FAILED ---
        if not execution_success:
            conditions_failed.append("execution_success is False")
            chain = VerdictChain(
                tier=VerdictTier.FAILED,
                status="failed",
                conditions_met=conditions_met,
                conditions_failed=conditions_failed,
                evidence_refs=evidence_refs,
                agenda_reconciliation=list(state.worklog[-5:]),
                field_verdict=field_verdict,
                coverage_snapshot=dict(coverage),
                mechanism_assessment_summary=assessment.summary,
                mechanism_blockers=list(assessment.blocking_conditions),
                assessed_at=now_iso(),
            )
            return {
                "status": "failed",
                "outcome": MissionOutcome.FAILED.value,
                "verdict_tier": VerdictTier.FAILED.value,
                "summary": "Execution evidence is insufficient or verification failed.",
                "verdict_chain": chain,
            }

        conditions_met.append("execution_success")

        # Determine data_success qualification
        has_extraction = coverage.get("extraction", 0.0) >= 0.3
        has_schema = coverage.get("schema", 0.0) >= 0.3
        has_field_evidence = any(
            fe.validation_status in {"validated", "partial"} for fe in field_evidence
        ) if field_evidence else has_extraction  # fall back to extraction coverage

        # Structural qualification: fields found with actionable selectors/paths.
        # Used for STRUCTURAL_SUCCESS and above — confirms the crawler can re-run.
        must_have_found = (
            all(
                any(
                    fe.field_name == fs.field_name and
                    fe.validation_status in {"validated", "partial"} and
                    fe.confidence >= 0.5 and
                    (fe.selector or fe.json_path)
                    for fe in field_evidence
                )
                for fs in must_have
            )
            if must_have and field_evidence
            else coverage.get("build", 0.0) >= 0.5  # fallback: build coverage
        )

        # Soft qualification: fields found by name + confidence, no selector required.
        # Used for DATA_SUCCESS — confirms data was returned even if extraction paths
        # are not yet pinned to specific selectors (e.g. page_extract mode).
        must_have_soft_found = (
            all(
                any(
                    fe.field_name == fs.field_name and
                    fe.validation_status in {"validated", "partial"} and
                    fe.confidence >= 0.5
                    for fe in field_evidence
                )
                for fs in must_have
            )
            if must_have and field_evidence
            else coverage.get("build", 0.0) >= 0.5  # fallback: build coverage
        )

        # --- MECHANISM_SUCCESS (best, check first) ---
        # NOTE: The ternary must be parenthesised to apply only to the hypothesis check,
        # NOT to the entire and-chain. Without parens, Python treats the ternary as:
        #   (whole_expression) if state.hypotheses else not mechanism_required
        # which makes mech_ok=True whenever hypotheses=[]+mechanism_required=False.
        mech_ok = (
            assessment.verdict == "validated"
            and coverage.get("reverse", 0.0) >= 0.75
            and coverage.get("protocol", 0.0) >= 0.75
            and not assessment.blocking_conditions
            and not state.mission.has_unresolved_agenda
            and (any(h.posterior >= 0.75 for h in state.hypotheses) if state.hypotheses else not state.mission.mechanism_required)
        )
        if mech_ok and must_have_found and has_field_evidence:
            conditions_met.append("mechanism_validated")
            conditions_met.append("structural_success")
            conditions_met.append("data_success")
            tier = VerdictTier.MECHANISM_SUCCESS
            status = "success"
        elif (
            not state.mission.mechanism_required
            and has_field_evidence
            and coverage.get("verify", 0.0) >= 0.7
            and not state.mission.has_unresolved_agenda
        ):
            # --- OPERATIONAL_SUCCESS ---
            conditions_met.append("no_mechanism_required")
            conditions_met.append("data_success")
            conditions_met.append("all_agenda_closed")
            if assessment.blocking_conditions:
                conditions_failed.append(f"mechanism_blockers_present: {assessment.blocking_conditions}")
                tier = VerdictTier.PARTIAL_SUCCESS
                status = "partial"
            else:
                tier = VerdictTier.OPERATIONAL_SUCCESS
                status = "success"
        elif must_have_found and has_field_evidence and not assessment.blocking_conditions:
            # --- STRUCTURAL_SUCCESS ---
            conditions_met.append("must_have_fields_validated")
            conditions_met.append("data_success")
            tier = VerdictTier.STRUCTURAL_SUCCESS
            status = "success"
        elif has_extraction and has_field_evidence:
            # --- DATA_SUCCESS ---
            # Data was extracted regardless of mechanism validation status.
            # Distinguish between two kinds of blockers:
            #   • Execution blockers: captcha/blocked/no-data — data was NOT actually returned.
            #   • Mechanism blockers: missing signature spec, unresolved headers — these are
            #     expected research outcomes when mechanism closure is unproven. They should
            #     NOT prevent DATA_SUCCESS when data was actually extracted, because the
            #     system made its best effort and delivered real results.
            # Note: uses must_have_soft_found (no selector required) because page_extract
            # mode returns fields by name+confidence without pinned CSS/JSON selectors.
            conditions_met.append("data_returned")
            execution_blockers = [
                c for c in (assessment.blocking_conditions or [])
                if any(kw in c.lower() for kw in ("blocked", "captcha", "no data", "no_data"))
            ]
            if execution_blockers or not must_have_soft_found:
                if execution_blockers:
                    conditions_failed.append(f"execution_blockers: {execution_blockers}")
                if not must_have_soft_found:
                    conditions_failed.append("not_all_must_have_fields_validated")
                tier = VerdictTier.PARTIAL_SUCCESS
                status = "partial"
            else:
                # Mechanism may be unproven, but data was returned. DATA_SUCCESS.
                if assessment.blocking_conditions:
                    conditions_met.append(f"mechanism_unproven_but_data_returned: {assessment.blocking_conditions}")
                tier = VerdictTier.DATA_SUCCESS
                status = "success"
        else:
            # --- EXECUTION_SUCCESS (minimum bar) ---
            conditions_failed.append("no_field_evidence_or_extraction")
            tier = VerdictTier.EXECUTION_SUCCESS
            status = "partial"

        # Cap at PARTIAL_SUCCESS if there are unresolved agenda items
        if state.mission.has_unresolved_agenda and VERDICT_RANK.get(tier.value, 0) > VERDICT_RANK[VerdictTier.PARTIAL_SUCCESS]:
            conditions_failed.append("verdict_capped: unresolved agenda items remain")
            tier = VerdictTier.PARTIAL_SUCCESS
            status = "partial"

        chain = VerdictChain(
            tier=tier,
            status=status,
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
            evidence_refs=evidence_refs,
            agenda_reconciliation=[
                a for a in (state.worklog or [])
                if any(kw in a for kw in ("AUTO_COMPLETE", "AUTO_FAIL", "NOT_APPLICABLE", "Agenda reconciled"))
            ][-10:],
            field_verdict=field_verdict,
            coverage_snapshot=dict(coverage),
            mechanism_assessment_summary=assessment.summary,
            mechanism_blockers=list(assessment.blocking_conditions),
            assessed_at=now_iso(),
        )
        # Legacy outcome for backwards compat
        legacy_outcome = TIER_TO_OUTCOME.get(tier.value, MissionOutcome.UNKNOWN.value)
        summary_map = {
            VerdictTier.MECHANISM_SUCCESS:   "Execution and mechanism evidence both reached closure.",
            VerdictTier.OPERATIONAL_SUCCESS: "Operational objective succeeded without requiring mechanism closure.",
            VerdictTier.STRUCTURAL_SUCCESS:  "Extraction paths validated; all must-have fields confirmed.",
            VerdictTier.DATA_SUCCESS:        "Data returned and fields found, but some validation gaps remain.",
            VerdictTier.EXECUTION_SUCCESS:   "Code ran successfully but field-level evidence is incomplete.",
            VerdictTier.PARTIAL_SUCCESS:     "Partial success: execution succeeded but closure is incomplete.",
            VerdictTier.FAILED:              "Mission failed.",
        }
        return {
            "status": status,
            "outcome": legacy_outcome,
            "verdict_tier": tier.value,
            "summary": summary_map.get(tier, "Mission completed."),
            "verdict_chain": chain,
        }
