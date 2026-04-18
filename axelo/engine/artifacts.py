from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from axelo.config import settings
from axelo.engine.models import ArtifactBundle, ArtifactRecord, EngineRequest, MissionBrief, PrincipalAgentState
from axelo.utils.session_catalog import SessionCatalog


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        try:
            return value.value
        except Exception:
            return str(value)
    return value


class ArtifactManager:
    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = Path(workspace or settings.workspace)
        self.sessions_dir = self.workspace / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = SessionCatalog(self.sessions_dir)
        self.session_id = ""
        self.session_dir = Path()
        self.site_key = ""
        self.site_code = ""
        self.artifact_dir = Path()
        self.logs_dir = Path()
        self.generated_dir = Path()
        self.agent_runs_dir = Path()
        self.final_dir = Path()
        self._artifacts: list[ArtifactRecord] = []
        self._step_counter: int = 0
        self._event_seq: int = 0

    def create_session(self, request: EngineRequest, session_id: str = "") -> tuple[str, Path]:
        allocation = self.catalog.allocate(url_or_host=request.url, requested_session_id=session_id)
        self.session_id = allocation.session_id
        self.site_key = allocation.site_key
        self.site_code = allocation.site_code
        self.session_dir = allocation.session_dir
        self.artifact_dir = self.session_dir / "artifacts"
        self.logs_dir = self.session_dir / "logs"
        self.generated_dir = self.artifact_dir / "generated"
        self.agent_runs_dir = self.artifact_dir / "agent_runs"
        self.final_dir = self.artifact_dir / "final"
        for path in (self.session_dir, self.logs_dir, self.generated_dir, self.agent_runs_dir, self.final_dir, self.logs_dir / "principal_states"):
            path.mkdir(parents=True, exist_ok=True)
        request.session_id = self.session_id
        request.metadata["site_key"] = self.site_key
        request.metadata["site_code"] = self.site_code
        self._write_json(self.session_dir / "session_request.json", request)
        self._register_artifact("request", "session_request", self.session_dir / "session_request.json", "Original mission request.")
        events_path = self.logs_dir / "events.jsonl"
        events_path.touch(exist_ok=True)
        self._register_artifact("logs", "events", events_path, "Mission event stream.")
        return self.session_id, self.session_dir

    def write_mission_brief(self, brief: MissionBrief) -> None:
        path = self.final_dir / "mission_brief.json"
        self._write_json(path, brief)
        self._register_artifact("final", "mission_brief", path, "Mission framing generated before execution.")

    def write_principal_state(self, state: PrincipalAgentState, label: str = "current") -> None:
        current = self.logs_dir / "principal_state.json"
        snapshot = self.logs_dir / "principal_states" / f"{label}.json"
        self._write_json(current, state)
        self._write_json(snapshot, state)
        self._register_artifact("logs", "principal_state", current, "Latest principal mission state.")

    def append_event(self, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        self._event_seq += 1
        record = {
            "event_id": str(uuid.uuid4()),
            "seq": self._event_seq,
            "kind": kind,
            "message": message,
            "published_at": datetime.now().isoformat(),
            "data": _json_safe(data or {}),
        }
        line = json.dumps(record, ensure_ascii=False)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with (self.logs_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_agent_report(self, report: Any) -> None:
        self._step_counter += 1
        path = self.agent_runs_dir / f"{self._step_counter:02d}_{report.objective}.json"
        self._write_json(path, report)
        self._register_artifact("agent_runs", path.stem, path, f"Agent report for {report.objective}.")
        tool_results = getattr(report, "tool_results", {}) or {}
        for tool_name, output in tool_results.items():
            self._materialize_tool_output(tool_name, output)

    def finalize(
        self,
        *,
        principal_state: PrincipalAgentState,
        mission_brief: MissionBrief | None,
        success: bool,
        execution_success: bool,
    ) -> ArtifactBundle:
        blockers = list(principal_state.trust.blockers)
        if not blockers and principal_state.mission.status == "failed" and principal_state.mission.current_uncertainty:
            blockers = [principal_state.mission.current_uncertainty]
        mission_report = {
            "session_id": self.session_id,
            "site_key": self.site_key,
            "site_code": self.site_code,
            "success": success,
            "execution_success": execution_success,
            "mission_status": principal_state.mission.status,
            "mission_outcome": principal_state.mission.outcome,
            "objective": principal_state.mission.objective,
            "target_url": principal_state.mission.target_url,
            "current_uncertainty": principal_state.mission.current_uncertainty,
            "trust": {
                "score": principal_state.trust.score,
                "level": principal_state.trust.level,
                "execution_score": principal_state.trust.execution_score,
                "mechanism_score": principal_state.trust.mechanism_score,
            },
            "blockers": blockers,
            "next_action_hint": principal_state.next_action_hint,
            "worklog": list(principal_state.worklog[-20:]),
            "open_questions": list(principal_state.open_questions),
            "mission_brief": _json_safe(mission_brief) if mission_brief else None,
        }
        mission_path = self.final_dir / "mission_report.json"
        evidence_path = self.final_dir / "evidence_graph.json"
        self._write_json(mission_path, mission_report)
        self._write_json(evidence_path, principal_state.evidence_graph)
        self._register_artifact("final", "mission_report", mission_path, "Final mission outcome summary.")
        self._register_artifact("final", "evidence_graph", evidence_path, "Evidence graph for the completed mission.")
        index = {
            "session_id": self.session_id,
            "site_key": self.site_key,
            "site_code": self.site_code,
            "success": success,
            "execution_success": execution_success,
            "artifacts": [_json_safe(item) for item in self._artifacts],
        }
        index_path = self.final_dir / "artifact_index.json"
        self._write_json(index_path, index)
        self._register_artifact("final", "artifact_index", index_path, "Index of generated artifacts.")
        return ArtifactBundle(
            session_id=self.session_id,
            root_dir=str(self.session_dir),
            index_path=str(index_path),
            artifacts=list(self._artifacts),
            summary=f"Generated {len(self._artifacts)} artifacts under {self.session_dir}",
        )

    def _materialize_tool_output(self, tool_name: str, output: dict[str, Any]) -> None:
        if tool_name == "codegen":
            python_code = str(output.get("python_code") or "")
            js_code = str(output.get("js_code") or "")
            manifest = output.get("manifest") or {}
            if python_code:
                path = self.generated_dir / "crawler.py"
                path.write_text(python_code, encoding="utf-8")
                self._register_artifact("generated", "crawler", path, "Generated crawler source.")
            if js_code:
                path = self.generated_dir / "signature.js"
                path.write_text(js_code, encoding="utf-8")
                self._register_artifact("generated", "signature_bridge", path, "Generated JS bridge.")
            if manifest:
                path = self.generated_dir / "manifest.json"
                self._write_json(path, manifest)
                self._register_artifact("generated", "manifest", path, "Generated crawler manifest.")
            return
        if tool_name == "verify":
            path = self.final_dir / "verify_output.json"
            self._write_json(path, output)
            self._register_artifact("final", "verify_output", path, "Verification report.")
            return
        if tool_name == "runtime_hook":
            script = str(output.get("hook_script") or "")
            if script:
                path = self.generated_dir / "runtime_hook.js"
                path.write_text(script, encoding="utf-8")
                self._register_artifact("generated", "runtime_hook", path, "Runtime hook script.")

    def write_verdict_chain(self, verdict_chain: Any) -> None:
        """Write the VerdictChain audit record to artifacts/final/verdict_chain.json."""
        path = self.final_dir / "verdict_chain.json"
        self._write_json(path, verdict_chain)
        self._register_artifact("final", "verdict_chain", path, "Auditable verdict chain showing how the final verdict was determined.")

    def _register_artifact(self, category: str, name: str, path: Path, description: str) -> None:
        record = ArtifactRecord(category=category, name=name, path=str(path), description=description)
        if all(existing.path != record.path for existing in self._artifacts):
            self._artifacts.append(record)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
