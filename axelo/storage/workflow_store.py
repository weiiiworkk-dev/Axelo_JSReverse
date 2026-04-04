from __future__ import annotations

from pathlib import Path

import structlog
from pydantic import ValidationError

from axelo.models.trace import TraceArtifact

log = structlog.get_logger()


class WorkflowStore:
    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def trace_path(self, session_id: str) -> Path:
        return self._dir / session_id / "workflow_trace.json"

    def load(self, session_id: str) -> TraceArtifact | None:
        path = self.trace_path(session_id)
        if not path.exists():
            return None
        try:
            return TraceArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, OSError, ValueError) as exc:
            log.exception("workflow_trace_load_failed", session_id=session_id, error=str(exc))
            return None

    def save(self, session_id: str, trace: TraceArtifact) -> Path:
        path = self.trace_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        return path
