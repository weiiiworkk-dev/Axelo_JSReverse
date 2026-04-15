from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from axelo import tools as _registered_tools  # noqa: F401
from axelo.config import settings
from axelo.engine.artifacts import ArtifactManager
from axelo.engine.constitution import AgendaReconciler, EngineConstitution
from axelo.engine.models import (
    AgentExecutionResult,
    EnginePlan,
    EngineRequest,
    EngineRunResult,
    MissionOutcome,
    PreparedRun,
    PrincipalAgentState,
    TaskIntent,
)
from axelo.engine.principal import PrincipalDirector
from axelo.engine.subagents import SubAgentManager
from axelo.memory.db import MemoryDB
from axelo.memory.schema import ReverseSession
from axelo.tools.base import get_registry
from axelo.utils.domain import extract_site_domain


class UnifiedEngine:
    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = Path(workspace or settings.workspace)
        self.director = PrincipalDirector()
        self.subagents = SubAgentManager()
        self._thinking_callback: Callable[[str], None] | None = None
        self._event_callback: Callable[[str, str, dict[str, Any]], None] | None = None
        self._artifacts: dict[str, ArtifactManager] = {}

    def set_thinking_callback(self, callback: Callable[[str], None]) -> None:
        self._thinking_callback = callback

    def set_event_callback(self, callback: Callable[[str, str, dict[str, Any]], None]) -> None:
        self._event_callback = callback

    async def plan_request(
        self,
        *,
        prompt: str,
        url: str = "",
        goal: str = "",
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PreparedRun:
        request = EngineRequest(
            prompt=prompt.strip(),
            url=url.strip(),
            goal=goal.strip(),
            session_id=session_id,
            metadata=dict(metadata or {}),
        )
        artifact_manager = ArtifactManager(self.workspace)
        created_session_id, session_dir = artifact_manager.create_session(request, session_id=session_id)
        brief = self.director.synthesize_brief(request)
        artifact_manager.write_mission_brief(brief)
        plan = EnginePlan(
            session_id=created_session_id,
            summary=brief.summary,
            intent=TaskIntent(
                intent_type="mission_driven",
                confidence=0.9,
                reasoning="Mission is framed as evidence gaps and lines of inquiry.",
                requires_browser=bool(url),
            ),
            lines_of_inquiry=list(brief.lines_of_inquiry),
        )
        principal_state = self.director.bootstrap_state(request, plan, brief)
        artifact_manager.write_principal_state(principal_state, "planned")
        self._artifacts[created_session_id] = artifact_manager
        self._emit_event(
            "mission",
            "Mission brief prepared.",
            {"session_id": created_session_id, **self._state_payload(principal_state)},
        )
        return PreparedRun(
            request=request,
            plan=plan,
            session_id=created_session_id,
            session_dir=str(session_dir),
            principal_state=principal_state,
            mission_brief=brief,
        )

    async def execute_prepared(self, prepared: PreparedRun) -> EngineRunResult:
        artifact_manager = self._artifacts.get(prepared.session_id)
        if artifact_manager is None:
            raise ValueError(
                f"Session '{prepared.session_id}' has no registered artifact manager. "
                "Call plan_request() before execute_prepared()."
            )
        initial_input = self._initial_input(prepared.request)
        state = prepared.principal_state or self.director.bootstrap_state(prepared.request, prepared.plan, prepared.mission_brief or self.director.synthesize_brief(prepared.request))
        self.subagents.attach_session(session_id=prepared.session_id, initial_input=initial_input)
        self.subagents.ensure_default_agents(get_registry().list_tools())
        self.subagents.set_tool_start_callback(
            lambda tool_name: self._emit_thinking(f"Running tool: {tool_name}")
        )

        agent_results: list[AgentExecutionResult] = []
        max_steps = 12
        no_progress_rounds = 0
        for step in range(1, max_steps + 1):
            next_action = EngineConstitution.recommend_next_action(state)
            state.mission.current_focus = next_action.objective
            state.mission.current_uncertainty = next_action.reason
            state.last_review_reason = next_action.reason
            state.next_action_hint = next_action.objective
            state.objective_attempts[next_action.objective] = state.objective_attempts.get(next_action.objective, 0) + 1
            artifact_manager.write_principal_state(state, f"before_{step:02d}")

            if next_action.capability == "produce":
                break

            evidence_before = len(state.evidence)
            coverage_before = dict(state.evidence_graph.coverage)
            self._emit_event(
                "dispatch",
                next_action.reason,
                {"objective": next_action.objective, "step": step, "max_steps": max_steps, **self._state_payload(state)},
            )
            self._emit_thinking(f"Step {step}/{max_steps}: dispatching {next_action.objective}.")
            report = await self.subagents.execute_objective(
                objective=next_action.objective,
                objective_id=next_action.objective_id,
                initial_input=initial_input,
                task_params={
                    "objective_reason": next_action.reason,
                    "needed_evidence": list(next_action.needed_evidence),
                    "capability": next_action.capability,
                },
            )
            if report is None:
                import structlog as _sl
                _sl.get_logger().warning("subagent_returned_none", objective=next_action.objective, step=step)
                continue
            self.director.ingest_report(state, report)
            made_progress = self._made_progress(
                report=report,
                state=state,
                evidence_before=evidence_before,
                coverage_before=coverage_before,
            )
            if made_progress:
                no_progress_rounds = 0
                state.objective_stalls[next_action.objective] = 0
            else:
                no_progress_rounds += 1
                state.objective_stalls[next_action.objective] = state.objective_stalls.get(next_action.objective, 0) + 1
                stall_note = f"{next_action.objective} did not reduce uncertainty enough to justify repeated retries."
                if stall_note not in state.worklog:
                    state.worklog.append(stall_note)
                if stall_note not in state.open_questions:
                    state.open_questions.append(stall_note)
                state.last_review_reason = stall_note
                state.mission.current_uncertainty = stall_note
                if state.objective_stalls[next_action.objective] >= 2 or no_progress_rounds >= 2:
                    state.worklog.append("Mission halted after repeated non-progressing objectives.")
                    state.next_action_hint = "challenge_findings"
                    self.director.refresh_state(state)
            artifact_manager.write_agent_report(report)
            artifact_manager.write_principal_state(state, f"after_{step:02d}")
            agent_results.append(
                AgentExecutionResult(
                    task_id=report.objective_id,
                    tool_name=report.objective,
                    agent_role=report.agent_role,
                    success=report.success,
                    status="success" if report.success else "failed",
                    duration_seconds=report.duration_seconds,
                    output_keys=sorted(list(report.outputs.keys())),
                    error="; ".join(report.counterevidence),
                )
            )
            if state.objective_stalls.get(next_action.objective, 0) >= 2 or no_progress_rounds >= 2:
                break
            if next_action.objective == "verify_execution" and report.success and not state.trust.blockers:
                break

        execution_success = self._derive_execution_success(agent_results, state)

        # Phase 1 fix: mandatory agenda reconciliation BEFORE verdict classification
        coverage = EngineConstitution.evidence_coverage(state)
        recon_actions = AgendaReconciler.reconcile(state, coverage)
        if recon_actions:
            self._emit_event(
                "reconciliation",
                f"Agenda reconciled before verdict: {len(recon_actions)} action(s)",
                {"session_id": prepared.session_id, "actions": recon_actions, **self._state_payload(state)},
            )

        # Populate field-level evidence from contract if one was attached
        contract = getattr(prepared, "contract", None)
        if contract is not None:
            self._populate_field_evidence(state, contract)
            self._emit_event(
                "field_evidence",
                "Field evidence populated from execution results",
                {
                    "session_id": prepared.session_id,
                    "field_evidence": [fe.model_dump() for fe in getattr(contract, "field_evidence", [])],
                },
            )

        outcome = EngineConstitution.classify_outcome(state, execution_success, contract=contract)
        state.mission.phase = "complete"
        state.mission.status = outcome["status"]
        state.mission.outcome = outcome["outcome"]
        state.mission.verdict_tier = outcome.get("verdict_tier", outcome["outcome"])
        state.cognition_summary = outcome["summary"]
        state.mission.current_focus = ""
        if execution_success and outcome["status"] == "success":
            state.mission.current_uncertainty = ""
        self.director.refresh_state(state)
        artifact_manager.write_principal_state(state, "final")

        # Write verdict chain for auditing
        verdict_chain = outcome.get("verdict_chain")
        if verdict_chain is not None:
            artifact_manager.write_verdict_chain(verdict_chain)
            self._emit_event(
                "verdict",
                f"Mission verdict: {outcome.get('verdict_tier', outcome['outcome']).upper()}",
                {
                    "session_id": prepared.session_id,
                    "tier": outcome.get("verdict_tier", outcome["outcome"]),
                    "status": outcome["status"],
                    "conditions_met": getattr(verdict_chain, "conditions_met", []),
                    "conditions_failed": getattr(verdict_chain, "conditions_failed", []),
                    "coverage_snapshot": getattr(verdict_chain, "coverage_snapshot", {}),
                    **self._state_payload(state),
                },
            )

        self._persist_session_memory(prepared.request, state, execution_success)
        bundle = artifact_manager.finalize(
            principal_state=state,
            mission_brief=prepared.mission_brief,
            success=outcome["outcome"] != MissionOutcome.FAILED.value,
            execution_success=execution_success,
        )
        summary = self._build_summary(prepared.session_id, state, bundle.index_path)
        self._emit_event("complete", summary, {"session_id": prepared.session_id, "artifact_index": bundle.index_path, **self._state_payload(state)})
        return EngineRunResult(
            session_id=prepared.session_id,
            success=outcome["outcome"] != MissionOutcome.FAILED.value,
            summary=summary,
            plan=prepared.plan,
            agent_results=agent_results,
            artifact_bundle=bundle,
            principal_state=state,
            mission_brief=prepared.mission_brief,
            execution_success=execution_success,
            verdict_chain=outcome.get("verdict_chain"),
        )

    def _initial_input(self, request: EngineRequest) -> dict[str, Any]:
        requirements_meta = dict(request.metadata.get("requirements") or {})
        # Expose search_keyword at top level so browser/subagent tools can use it without
        # site-specific logic — keyword is stored in target_scope by the wizard.
        keyword = (requirements_meta.get("target_scope") or "").strip()
        return {
            "url": request.url,
            "target_url": request.url,
            "goal": request.effective_goal,
            "prompt": request.prompt,
            "search_keyword": keyword,
            "requirements_meta": requirements_meta,
        }

    def _derive_execution_success(self, agent_results: list[AgentExecutionResult], state: PrincipalAgentState | None) -> bool:
        verify_records = [record for record in (state.evidence if state else []) if record.kind == "verify"]
        if verify_records:
            latest = verify_records[-1]
            details = latest.details or {}
            verdict = str(details.get("execution_verdict") or details.get("success") or "").lower()
            return verdict in {"pass", "true"} or bool(details.get("success"))
        return any(result.tool_name == "verify_execution" and result.success for result in agent_results)

    def _made_progress(
        self,
        *,
        report: Any,
        state: PrincipalAgentState,
        evidence_before: int,
        coverage_before: dict[str, Any],
    ) -> bool:
        if not report.success:
            return False

        evidence_after = len(state.evidence)
        coverage_after = dict(state.evidence_graph.coverage)
        coverage_increased = any(
            float(coverage_after.get(key, 0.0)) > float(coverage_before.get(key, 0.0)) + 0.02
            for key in coverage_after
        )
        meaningful_outputs = bool(
            report.claims
            or report.outputs.get("mapped_fields")
            or report.outputs.get("listing_item_fields")
            or report.outputs.get("schema_fields")
            or report.outputs.get("runtime_sensitive_fields")
            or report.outputs.get("required_headers")
            or report.outputs.get("required_query_fields")
            or report.outputs.get("required_body_fields")
            or report.outputs.get("python_code")
            or report.outputs.get("success")
        )
        return coverage_increased or (evidence_after > evidence_before and meaningful_outputs)

    def _populate_field_evidence(self, state: PrincipalAgentState, contract: Any) -> None:
        """
        Maps extraction/build/verify evidence records to FieldEvidence entries on the contract.
        Called after the execution loop completes, before classify_outcome.
        """
        try:
            from axelo.models.contracts import FieldEvidence
        except ImportError:
            return

        requested_fields = getattr(contract, "requested_fields", [])
        if not requested_fields:
            return

        # Collect all extraction-relevant evidence records
        extraction_evidence = [
            e for e in state.evidence
            if e.kind in ("extraction", "build", "verify", "schema", "response_schema")
        ]

        existing_names = {fe.field_name for fe in getattr(contract, "field_evidence", [])}
        new_evidence: list[FieldEvidence] = []

        for field_spec in requested_fields:
            if field_spec.field_name in existing_names:
                continue  # already populated (e.g. by a previous partial run)

            fe = FieldEvidence(field_name=field_spec.field_name)
            for ev in extraction_evidence:
                details = ev.details or {}
                # Check field_mapping first (builder-agent format)
                field_mapping = details.get("field_mapping") or {}
                entry = field_mapping.get(field_spec.field_name) or field_mapping.get(field_spec.field_alias or "")
                if entry and isinstance(entry, dict):
                    fe.found = True
                    fe.selector = str(entry.get("selector", ""))
                    fe.json_path = str(entry.get("json_path", ""))
                    fe.extractor = str(entry.get("extractor", "css"))
                    raw_samples = entry.get("sample_values") or []
                    fe.sample_values = [str(v) for v in raw_samples[:5]]
                    fe.confidence = float(entry.get("confidence", 0.5))
                    fe.source_evidence_id = ev.evidence_id
                    fe.validation_status = "validated" if fe.confidence >= 0.7 else "partial"
                    break
                # Fallback: check mapped_fields list (schema-agent format)
                mapped = details.get("mapped_fields") or details.get("listing_item_fields") or []
                if isinstance(mapped, list) and field_spec.field_name in mapped:
                    fe.found = True
                    fe.extractor = "css"
                    fe.confidence = float(ev.confidence) if ev.confidence else 0.4
                    fe.source_evidence_id = ev.evidence_id
                    fe.validation_status = "partial"
                    break

            if not fe.found:
                fe.validation_status = "missing"
            new_evidence.append(fe)

        if new_evidence:
            contract.field_evidence.extend(new_evidence)

    def _persist_session_memory(self, request: EngineRequest, state: PrincipalAgentState, execution_success: bool) -> None:
        import structlog as _sl
        _log = _sl.get_logger()
        try:
            db = MemoryDB(self.workspace / "memory" / "engine_memory.db")
            session = ReverseSession(
                session_id=state.mission.session_id,
                url=request.url,
                domain=extract_site_domain(request.url) or request.url,
                goal=request.effective_goal,
                difficulty="medium",
                algorithm_type=state.mechanism.dominant_hypothesis_id or "unknown",
                codegen_strategy="mission_driven",
                ai_confidence=state.trust.score,
                verified=state.mission.outcome == MissionOutcome.MECHANISM_VALIDATED.value,
                duration_seconds=0.0,
                experience_summary=state.cognition_summary,
                static_features="",
                hook_trace_summary="",
                hypothesis_json="",
            )
            db.save_session(session)
        except Exception as exc:
            _log.error("session_memory_persistence_failed", error=str(exc), session_id=state.mission.session_id)

    def _build_summary(self, session_id: str, state: PrincipalAgentState, artifact_index: str) -> str:
        return f"Session {session_id} finished with {state.mission.outcome}. Artifact index: {artifact_index}"

    def _state_payload(self, state: PrincipalAgentState) -> dict[str, Any]:
        return {
            "mission_status": state.mission.status,
            "mission_outcome": state.mission.outcome,
            "current_focus": state.mission.current_focus,
            "current_uncertainty": state.mission.current_uncertainty,
            "evidence_count": len(state.evidence),
            "hypothesis_count": len(state.hypotheses),
            "coverage": dict(state.evidence_graph.coverage),
            "trust_score": state.trust.score,
            "trust_level": state.trust.level,
            "trust_summary": state.trust.summary,
            "execution_trust_score": state.trust.execution_score,
            "execution_trust_level": state.trust.execution_level,
            "execution_trust_summary": state.trust.execution_summary,
            "mechanism_trust_score": state.trust.mechanism_score,
            "mechanism_trust_level": state.trust.mechanism_level,
            "mechanism_trust_summary": state.trust.mechanism_summary,
            "dominant_hypothesis": state.mechanism.dominant_hypothesis_id,
            "mechanism_blockers": list(state.mechanism.blocking_conditions),
            "next_action_hint": state.next_action_hint,
            "evidence_delta": state.evidence_delta,
        }

    def _emit_thinking(self, message: str) -> None:
        if self._thinking_callback:
            self._thinking_callback(message)

    def _emit_event(self, kind: str, message: str, payload: dict[str, Any]) -> None:
        artifact_manager = self._artifacts.get(payload.get("session_id", ""))
        if artifact_manager:
            artifact_manager.append_event(kind, message, payload)
        if self._event_callback:
            self._event_callback(kind, message, payload)
