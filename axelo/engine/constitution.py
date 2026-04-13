from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axelo.engine.models import MechanismAssessment, MissionOutcome, NextActionSpec, PrincipalAgentState


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
                verdict = str(details.get("execution_verdict") or details.get("success") or "").lower()
                if verdict in {"pass", "true"}:
                    value = max(value, 0.85)
                coverage["verify"] = max(coverage["verify"], value)
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
        if not explained["transport"]:
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

        if coverage["acquisition"] < 0.55:
            return NextActionSpec(
                objective_id="objective:surface",
                objective="discover_surface",
                capability="recon",
                reason="The principal surface is not grounded yet.",
                needed_evidence=["page capture", "bundle references", "observed requests"],
            )
        if coverage["protocol"] < 0.55:
            return NextActionSpec(
                objective_id="objective:transport",
                objective="recover_transport",
                capability="transport",
                reason="Transport-sensitive fields are still under-specified.",
                needed_evidence=["request fields", "headers", "cookies"],
            )
        if state.mission.mechanism_required and coverage["reverse"] < 0.55:
            return NextActionSpec(
                objective_id="objective:reverse",
                objective="recover_static_mechanism",
                capability="reverse",
                reason="Mechanism claims lack static or signature evidence.",
                needed_evidence=["static candidates", "signature inputs", "algorithm hints"],
            )
        if state.mission.mechanism_required and coverage["runtime"] < 0.55:
            return NextActionSpec(
                objective_id="objective:runtime",
                objective="recover_runtime_mechanism",
                capability="runtime",
                reason="Runtime-sensitive evidence is still missing.",
                needed_evidence=["hook points", "runtime fields", "fingerprint sources"],
            )
        if coverage["schema"] < 0.55:
            if stalled_schema >= 1:
                # If surface and protocol are solid, bypass stalled schema recovery and attempt
                # artifact generation directly using whatever DOM/HTML evidence is available.
                # This prevents the system from looping in challenge_findings when the target
                # serves HTML listings that have no embedded JSON schema.
                if coverage["acquisition"] >= 0.65 and coverage["protocol"] >= 0.55:
                    return NextActionSpec(
                        objective_id="objective:build",
                        objective="build_artifacts",
                        capability="builder",
                        reason="Schema recovery stalled; acquisition and protocol evidence is sufficient to generate extraction artifacts from available HTML/DOM evidence.",
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
    def classify_outcome(cls, state: PrincipalAgentState | None, execution_success: bool) -> dict[str, str]:
        if state is None:
            return {
                "status": "failed",
                "outcome": MissionOutcome.FAILED.value,
                "summary": "Mission state was unavailable.",
            }
        assessment = cls.mechanism_assessment(state)
        if not execution_success:
            return {
                "status": "failed",
                "outcome": MissionOutcome.FAILED.value,
                "summary": "Execution evidence is insufficient or verification failed.",
            }
        if assessment.verdict == "validated":
            return {
                "status": "success",
                "outcome": MissionOutcome.MECHANISM_VALIDATED.value,
                "summary": "Execution and mechanism evidence both reached closure.",
            }
        # If mechanism is not required (simple crawl / operational task), report
        # operational success regardless of mechanism evidence depth.
        if not state.mission.mechanism_required:
            return {
                "status": "success",
                "outcome": MissionOutcome.OPERATIONAL_SUCCESS.value,
                "summary": "Operational objective succeeded without requiring mechanism closure.",
            }
        if assessment.verdict == "partial":
            return {
                "status": "partial",
                "outcome": MissionOutcome.MECHANISM_PARTIAL.value,
                "summary": "Execution succeeded, but mechanism evidence is only partial.",
            }
        if state.mission.mechanism_required:
            return {
                "status": "partial",
                "outcome": MissionOutcome.REPLAY_SUCCESS.value,
                "summary": "Execution succeeded through replay or incomplete mechanism evidence.",
            }
        return {
            "status": "success",
            "outcome": MissionOutcome.OPERATIONAL_SUCCESS.value,
            "summary": "Operational objective succeeded without requiring mechanism closure.",
        }
