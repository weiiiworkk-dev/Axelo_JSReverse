from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any

from axelo.engine.constitution import EngineConstitution
from axelo.engine.models import (
    AgentReport,
    AgendaRecord,
    BranchRecord,
    EnginePlan,
    EngineRequest,
    EvidenceLink,
    EvidenceRecord,
    HypothesisRecord,
    MissionBrief,
    MissionOutcome,
    MissionState,
    PrincipalAgentState,
    TaskIntent,
    now_iso,
)


class PrincipalDirector:
    def synthesize_brief(self, request: EngineRequest) -> MissionBrief:
        objective = request.effective_goal or "Investigate the target and produce a working extraction path."
        target = request.url or "unspecified target"
        lines_of_inquiry = [
            "Establish the primary data surface and the acquisition path.",
            "Recover transport-sensitive fields and session constraints.",
            "Discriminate replay-only success from real mechanism understanding.",
            "Generate and verify only after evidence is strong enough.",
        ]
        if not EngineConstitution.infer_mechanism_required(objective):
            lines_of_inquiry[2] = "Keep mechanism analysis proportional to the requested outcome."
        assumptions = [
            f"Target: {target}",
            f"Mission: {objective}",
        ]
        success_criteria = [
            "Primary data surface is identified with evidence.",
            "Extraction path is mapped to concrete fields or DOM selectors.",
            "Generated artifacts are verified against the mission.",
        ]
        if EngineConstitution.infer_mechanism_required(objective):
            success_criteria.insert(2, "Mechanism claims are supported by runtime or transport evidence.")
        return MissionBrief(
            title="Mission Brief",
            summary=f"Drive the session from mission evidence, not from a preset tool chain. Objective: {objective}",
            lines_of_inquiry=lines_of_inquiry,
            assumptions=assumptions,
            success_criteria=success_criteria,
        )

    def bootstrap_state(self, request: EngineRequest, plan: EnginePlan, brief: MissionBrief) -> PrincipalAgentState:
        mission = MissionState(
            session_id=plan.session_id or request.session_id,
            target_url=request.url,
            objective=request.effective_goal,
            phase="planned",
            status="active",
            outcome=MissionOutcome.UNKNOWN.value,
            current_focus="frame the mission and gather first-hand evidence",
            current_uncertainty="Need initial acquisition evidence before committing to transport, schema, or mechanism claims.",
            success_criteria=list(brief.success_criteria),
            constraints=[
                text
                for text in (
                    str((request.metadata.get("requirements") or {}).get("auth_notes") or "").strip(),
                    str((request.metadata.get("requirements") or {}).get("constraints") or "").strip(),
                    str((request.metadata.get("requirements") or {}).get("output_expectation") or "").strip(),
                )
                if text
            ],
            mechanism_required=EngineConstitution.infer_mechanism_required(request.effective_goal),
        )
        hypotheses = [
            HypothesisRecord(
                hypothesis_id="surface:primary-data",
                statement="The target exposes a primary data surface that can be recovered from page, transport, or replay evidence.",
                mechanism_class="surface",
                confidence=0.35,
                prior=0.35,
                posterior=0.35,
                next_probe="discover_surface",
            ),
            HypothesisRecord(
                hypothesis_id="mechanism:replay",
                statement="Stable replay and session reuse may be sufficient for the mission outcome.",
                mechanism_class="replay",
                confidence=0.25,
                prior=0.25,
                posterior=0.25,
                next_probe="verify_execution",
            ),
            HypothesisRecord(
                hypothesis_id="mechanism:runtime",
                statement="A runtime-derived token, fingerprint, or time-sensitive field materially changes success.",
                mechanism_class="runtime",
                confidence=0.25,
                prior=0.25,
                posterior=0.25,
                next_probe="recover_runtime_mechanism",
            ),
            HypothesisRecord(
                hypothesis_id="mechanism:transport",
                statement="Transport-sensitive headers, cookies, or query fields explain the guarded surface.",
                mechanism_class="transport",
                confidence=0.15,
                prior=0.15,
                posterior=0.15,
                next_probe="recover_transport",
            ),
        ]
        agenda = [
            AgendaRecord(item_id="mission:surface", label="Find primary data surface", owner="principal", rationale=brief.lines_of_inquiry[0]),
            AgendaRecord(item_id="mission:transport", label="Recover guarded fields", owner="principal", rationale=brief.lines_of_inquiry[1]),
            AgendaRecord(item_id="mission:build", label="Build only after evidence is grounded", owner="principal", rationale=brief.lines_of_inquiry[-1]),
        ]
        branches = [
            BranchRecord(
                branch_id="main",
                label="main",
                status="active",
                score=0.5,
                budget_weight=1.0,
                rationale="Primary mission branch.",
                focus="mission bootstrap",
            )
        ]
        state = PrincipalAgentState(
            mission=mission,
            agenda=agenda,
            hypotheses=hypotheses,
            branches=branches,
            active_branch_id="main",
            open_questions=[
                "What is the primary data surface?",
                "What fields or headers appear to gate access?",
                "Does the mission require real mechanism closure or only operational success?",
            ],
            cognition_summary=brief.summary,
            worklog=["Mission bootstrapped from request."],
        )
        self.refresh_state(state)
        return state

    def ingest_report(self, state: PrincipalAgentState, report: AgentReport) -> None:
        state.evidence.extend(report.evidence)
        state.worklog.append(report.summary)
        for claim in report.claims[:4]:
            if claim not in state.worklog:
                state.worklog.append(f"claim: {claim}")
        for question in report.recommended_questions:
            if question not in state.open_questions:
                state.open_questions.append(question)

        if report.objective == "discover_surface":
            self._mark_agenda(state, "mission:surface", "completed", report.summary)
        elif report.objective in {"recover_transport", "recover_runtime_mechanism", "recover_static_mechanism"}:
            self._mark_agenda(state, "mission:transport", "in_progress", report.summary)
        elif report.objective in {"build_artifacts", "verify_execution"}:
            self._mark_agenda(state, "mission:build", "in_progress", report.summary)

        self._update_hypotheses(state, report)
        self._rebuild_evidence_graph(state)
        self.refresh_state(state)

    def refresh_state(self, state: PrincipalAgentState) -> None:
        trust = EngineConstitution.trust_score(state)
        state.trust.score = trust["score"]
        state.trust.level = trust["level"]
        state.trust.summary = trust["summary"]
        execution = trust["execution"]
        mechanism = trust["mechanism"]
        state.trust.execution_score = execution["score"]
        state.trust.execution_level = execution["level"]
        state.trust.execution_summary = execution["summary"]
        state.trust.mechanism_score = mechanism["score"]
        state.trust.mechanism_level = mechanism["level"]
        state.trust.mechanism_summary = mechanism["summary"]
        state.trust.indicators = dict(trust["indicators"])
        assessment = EngineConstitution.mechanism_assessment(state)
        state.mechanism = assessment
        state.trust.blockers = list(assessment.blocking_conditions)
        state.evidence_graph.coverage = EngineConstitution.evidence_coverage(state)
        state.evidence_graph.updated_at = now_iso()
        state.next_action_hint = EngineConstitution.recommend_next_action(state).objective
        state.evidence_delta = self._summarize_evidence_delta(state)
        state.updated_at = now_iso()

    def _mark_agenda(self, state: PrincipalAgentState, item_id: str, status: str, rationale: str) -> None:
        # Single-threaded context: find first, then mutate atomically to reduce iteration-time mutation window.
        target = next((item for item in state.agenda if item.item_id == item_id), None)
        if target is not None:
            target.status = status
            target.rationale = rationale
            target.updated_at = now_iso()

    def _update_hypotheses(self, state: PrincipalAgentState, report: AgentReport) -> None:
        coverage = EngineConstitution.evidence_coverage(state)
        for hypothesis in state.hypotheses:
            if hypothesis.mechanism_class == "surface":
                hypothesis.posterior = max(hypothesis.posterior, coverage.get("acquisition", 0.0))
            elif hypothesis.mechanism_class == "transport":
                hypothesis.posterior = max(hypothesis.posterior, coverage.get("protocol", 0.0))
            elif hypothesis.mechanism_class == "runtime":
                hypothesis.posterior = max(hypothesis.posterior, coverage.get("runtime", 0.0))
            elif hypothesis.mechanism_class == "replay":
                hypothesis.posterior = max(hypothesis.posterior, coverage.get("verify", 0.0) * 0.8)
            hypothesis.confidence = hypothesis.posterior
            if report.objective.startswith("recover_") and hypothesis.next_probe == report.objective:
                hypothesis.support_score = min(1.0, hypothesis.support_score + 0.15)
            if report.objective == "challenge_findings" and report.counterevidence:
                hypothesis.refute_score = min(1.0, hypothesis.refute_score + 0.1)
        dominant = max(state.hypotheses, key=lambda item: item.posterior, default=None)
        if dominant:
            state.mechanism.dominant_hypothesis_id = dominant.hypothesis_id

    def _rebuild_evidence_graph(self, state: PrincipalAgentState) -> None:
        links: list[EvidenceLink] = []
        previous: EvidenceRecord | None = None
        for record in state.evidence:
            if previous is not None:
                links.append(
                    EvidenceLink(
                        link_id=f"{previous.evidence_id}->{record.evidence_id}",
                        relation="precedes",
                        source_id=previous.evidence_id,
                        target_id=record.evidence_id,
                        summary="Evidence observed later in the same mission.",
                        confidence=0.5,
                    )
                )
            previous = record
        state.evidence_graph.nodes = deepcopy(list(state.evidence))
        state.evidence_graph.links = links
        dominant = max(state.hypotheses, key=lambda item: item.posterior, default=None)
        state.evidence_graph.dominant_hypothesis_id = dominant.hypothesis_id if dominant else ""

    def _summarize_evidence_delta(self, state: PrincipalAgentState) -> str:
        coverage = EngineConstitution.evidence_coverage(state)
        ranked = sorted(coverage.items(), key=lambda item: item[1], reverse=True)
        preview = ", ".join(f"{name}={value:.2f}" for name, value in ranked[:3])
        return f"Coverage snapshot: {preview}" if preview else ""


class IntakeAIProcessor:
    """
    AI-mediated intake processor for the chat-first requirement flow.
    Processes natural language user messages and updates MissionContract accordingly.
    Called by the /api/intake/{id}/chat endpoint.
    """

    SYSTEM_PROMPT = """You are Axelo's intake specialist for an AI-driven web reverse engineering and crawling workbench.
Your role: understand the user's requirements from natural language and produce a structured MissionContract.

CURRENT CONTRACT STATE:
{contract_json}

CHAT HISTORY (last {history_count} turns):
{history_json}

USER MESSAGE:
{user_message}

LANGUAGE RULES (CRITICAL):
- "ai_reply" MUST be written in Chinese (简体中文). This is the conversational response shown to the user.
  Regardless of what language the user writes in, always reply to them in Chinese.
- All contract_patch field VALUES that are free-form English text (objective, field_name, field_alias,
  description, assumptions, constraints, etc.) MUST be written in English.
  Structured fields like URLs, field names, type strings, and enum values are always English.
- The user sees "ai_reply" in Chinese and the contract fields in English — these are separate concerns.

RULES:
1. Extract specific, verifiable objectives from vague language.
2. Infer reasonable defaults silently (e.g. "a few results" → item_limit=50, no auth → mechanism="none").
3. Ask at most ONE clarifying question per turn, and ONLY for blocking_gaps that prevent execution.
4. If user says "just start" / "figure it out" / is impatient: set confidence 0.65, fill plausible defaults.
5. Set confidence as a rough self-assessment of how complete the contract feels (0.0–1.0). It is display-only — the backend ignores it for start gating. Readiness is determined solely by blocking_gaps being empty.
6. Never ask about stealth/concurrency/timeouts unless the user mentions anti-bot problems.
7. Mark non-obvious inferences in the assumptions list as "Assumed: <thing>" (in English).
8. For objective_type: use "reverse_engineer" if user mentions tokens/signing/auth/fingerprint/anti-bot; else use "extract_data" for crawling/scraping.
9. mechanism_required: true if objective_type is "reverse_engineer", false otherwise.

AUTO-INFERRED DEFAULTS (apply silently, no need to ask):
- "a few" / "some" → item_limit: 50
- "all fields" → infer FieldSpec list from objective context
- no output format → format: "json"
- no rate limit → requests_per_sec: 1.0
- no auth mentioned → auth mechanism: "none", login_required: false

RESPOND WITH EXACTLY THIS JSON (no markdown, no extra keys):
{
  "ai_reply": "<用中文和用户沟通，1-4句话>",
  "contract_patch": {<only the fields that changed — ALL TEXT VALUES IN ENGLISH>},
  "readiness_assessment": {
    "confidence": <0.0-1.0 float>,
    "is_ready": <bool — true only when all hard requirements met>,
    "missing_info": [<non-blocking gaps in English, can be empty>],
    "blocking_gaps": [<gaps that PREVENT execution in English, e.g. "No valid target URL">],
    "suggestions": [<at most one question string in English, or empty list>]
  }
}"""

    def __init__(self, client: Any = None) -> None:
        self._client = client

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from axelo.ai.client import get_client  # type: ignore
        return get_client()

    async def process_message(
        self,
        message: str,
        contract: Any,  # MissionContract
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Process a user message during intake.
        Returns: {ai_reply, updated_contract, readiness, contract_delta}
        """
        from axelo.models.contracts import ReadinessAssessment

        contract_json = contract.model_dump_json(indent=2) if hasattr(contract, "model_dump_json") else json.dumps(contract, indent=2, default=str)
        history_json = json.dumps(history[-8:], ensure_ascii=False, indent=2)  # last 8 turns

        # Use str.replace instead of .format() to avoid KeyError on literal { } in the JSON template section
        prompt = (
            self.SYSTEM_PROMPT
            .replace("{contract_json}", contract_json)
            .replace("{history_count}", str(len(history)))
            .replace("{history_json}", history_json)
            .replace("{user_message}", message)
        )

        import logging as _logging
        _intake_log = _logging.getLogger(__name__)

        raw = ""
        parsed: dict[str, Any] = {}
        _last_exc: Exception | None = None

        for _attempt in range(2):  # one retry on transient errors
            try:
                client = await self._get_client()
                raw = await client.complete(prompt, max_tokens=800, temperature=0.3)
                # Strip markdown code fences if present
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[: raw.rfind("```")]
                parsed = json.loads(raw)
                _last_exc = None
                break  # success
            except json.JSONDecodeError as _jexc:
                # Attempt brace-extraction fallback before giving up
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        parsed = json.loads(raw[start:end])
                        _last_exc = None
                        break  # recovered via brace extraction
                    except Exception:
                        pass
                # Fallback failed — treat as transient (model may have returned
                # non-JSON prose) and retry once, then fall through to empty parsed
                _last_exc = _jexc
                _intake_log.warning(
                    "IntakeAIProcessor JSON parse failed (attempt %d/2): %s",
                    _attempt + 1, raw[:120],
                )
                if _attempt == 0:
                    import asyncio as _aio
                    await _aio.sleep(1)
            except Exception as _exc:
                _last_exc = _exc
                _intake_log.warning(
                    "IntakeAIProcessor API call failed (attempt %d/2): %s: %s",
                    _attempt + 1, type(_exc).__name__, _exc,
                )
                if _attempt == 0:
                    import asyncio as _aio
                    await _aio.sleep(2)  # brief wait before retry

        if _last_exc is not None:
            _intake_log.error(
                "IntakeAIProcessor: all attempts failed, returning fallback. Last error: %s", _last_exc
            )

        ai_reply = str(parsed.get("ai_reply") or "I've noted your requirements. Please provide a target URL if you haven't already.")
        contract_patch = parsed.get("contract_patch") or {}
        raw_readiness = parsed.get("readiness_assessment") or {}

        # Apply patch to contract
        updated_contract = self._apply_patch(contract, contract_patch)
        # Compute final readiness with hard overrides
        readiness = self._compute_readiness(updated_contract, raw_readiness)
        updated_contract.readiness_assessment = readiness
        updated_contract.source_chat_turns = updated_contract.source_chat_turns + 1
        updated_contract.last_updated_by = "ai_intake"
        updated_contract.contract_version = updated_contract.contract_version + 1

        return {
            "ai_reply": ai_reply,
            "updated_contract": updated_contract,
            "readiness": readiness,
            "contract_delta": contract_patch,
        }

    # ── Field permission sets for _apply_patch() ─────────────────────────────

    # Nested Pydantic model fields — must deep-merge (subfield update), not replace
    _NESTED_FIELDS: frozenset[str] = frozenset({
        "target_scope", "auth_spec", "execution_spec", "output_spec",
    })

    # Fields the AI intake processor is allowed to write
    _AI_WRITABLE: frozenset[str] = frozenset({
        "target_url", "objective", "objective_type", "mechanism_required",
        "item_limit", "page_limit", "constraints", "exclusions", "assumptions",
        "requested_fields",
        "target_scope", "auth_spec", "execution_spec", "output_spec",
    })

    # Fields that only the system may write — AI patch must never touch these
    _SYSTEM_ONLY: frozenset[str] = frozenset({
        "contract_id", "session_id", "created_at", "locked_at",
        "contract_version", "source_chat_turns", "last_updated_by",
        "field_evidence", "readiness_assessment",
    })

    def _apply_patch(self, contract: Any, patch: dict[str, Any]) -> Any:
        """
        Apply a partial patch dict to the MissionContract with typed deep merge.

        Rules:
        - Locked contracts are returned unchanged (hard stop).
        - SYSTEM_ONLY fields are silently ignored in patch.
        - Unknown fields (not in AI_WRITABLE) are silently ignored.
        - NESTED_FIELDS: subfields deep-merged (existing subfields preserved).
        - requested_fields (list): full replacement when AI provides it.
        - All other AI_WRITABLE scalar fields: direct overwrite.
        """
        if not patch:
            return contract
        # Locked contracts are immutable — reject all AI patches
        if getattr(contract, "is_locked", False):
            return contract
        try:
            from axelo.models.contracts import MissionContract
            current = contract.model_dump()

            for key, value in patch.items():
                if key in self._SYSTEM_ONLY:
                    continue  # AI cannot write system fields
                if key not in self._AI_WRITABLE:
                    continue  # Unknown or disallowed field — silently ignore

                if (
                    key in self._NESTED_FIELDS
                    and isinstance(value, dict)
                    and isinstance(current.get(key), dict)
                ):
                    # Deep merge: preserve existing subfields, update only what AI provided
                    current[key] = {**current[key], **value}
                else:
                    # Scalar or list (requested_fields) — direct replacement
                    current[key] = value

            return MissionContract(**current)
        except Exception:
            return contract

    # Trivial objective strings that should not count as "executable objectives"
    _TRIVIAL_OBJECTIVES: frozenset[str] = frozenset({
        "crawl", "scrape", "extract", "get data", "get info", "get information",
        "collect", "fetch", "download", "grab", "pull",
        "爬取", "抓取", "获取", "爬虫", "抓数据",
    })

    def _compute_readiness(self, contract: Any, ai_assessment: dict[str, Any]) -> Any:
        """
        Compute ReadinessAssessment using deterministic gate checks as the primary
        authority. AI-reported confidence is display-only and never read by gate logic.

        User-visible gate list (all must pass for is_ready=True):
          1. Valid target URL (http:// or https://)
          2. Non-trivial objective (> 15 chars and not a bare keyword)
          3. At least one data signal (FieldSpec list OR objective_type set)
          4. No AI-reported blocking gaps

        Internal sanity check (silent, no user-facing message):
          - contract_version >= 1: AI has processed the contract at least once
        """
        from axelo.models.contracts import ReadinessAssessment

        gates: list[str] = []

        # Gate 1: Valid URL
        target_url = (getattr(contract, "target_url", "") or "").strip()
        if not target_url or not target_url.startswith(("http://", "https://")):
            gates.append("No valid target URL (must start with http:// or https://)")

        # Gate 2: Executable objective
        objective = (getattr(contract, "objective", "") or "").strip()
        if len(objective) < 15 or objective.lower() in self._TRIVIAL_OBJECTIVES:
            gates.append("Objective too vague — describe what data you want and from where")

        # Gate 3: At least one data signal
        has_fields = len(getattr(contract, "requested_fields", None) or []) > 0
        has_type = bool(getattr(contract, "objective_type", "") or "")
        if not has_fields and not has_type:
            gates.append("No fields or objective type — AI has not yet parsed your intent")

        # Internal sanity: contract never touched by AI → silent not-ready, no user-visible message
        # (Gate 3 already covers this state: version=0 implies no fields + no objective_type)
        if (getattr(contract, "contract_version", 0) or 0) < 1:
            from axelo.models.contracts import ReadinessAssessment
            return ReadinessAssessment(
                confidence=0.0,
                is_ready=False,
                missing_info=[],
                blocking_gaps=[],   # no user message — welcome state is its own feedback
                suggestions=[],
                assessed_at=datetime.now().isoformat(),
            )

        # Gate 4: No AI-reported blocking gaps
        ai_blocking = list(ai_assessment.get("blocking_gaps") or [])
        for gap in ai_blocking:
            if gap not in gates:
                gates.append(gap)

        # Confidence: display-only — passed through unchanged, never read by gate logic
        conf = float(ai_assessment.get("confidence") or 0.5)

        missing = list(ai_assessment.get("missing_info") or [])
        suggestions = list(ai_assessment.get("suggestions") or [])

        return ReadinessAssessment(
            confidence=round(conf, 2),
            is_ready=len(gates) == 0,
            missing_info=missing,
            blocking_gaps=gates,      # gates IS the authoritative blocking list
            suggestions=suggestions[:1],
            assessed_at=datetime.now().isoformat(),
        )
