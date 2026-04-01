from __future__ import annotations

from axelo.browser.trace_capture import append_checkpoint, new_trace
from axelo.models.trace import TraceArtifact
from axelo.storage import WorkflowStore


class WorkflowRuntime:
    def __init__(self, store: WorkflowStore) -> None:
        self._store = store

    def load_or_create(self, session_id: str) -> TraceArtifact:
        trace = self._store.load(session_id)
        if trace is None:
            trace = new_trace()
            self._store.save(session_id, trace)
        return trace

    def checkpoint(
        self,
        session_id: str,
        trace: TraceArtifact,
        stage_name: str,
        status: str,
        summary: str = "",
        artifacts: dict[str, str] | None = None,
        manual_review: bool = False,
    ) -> TraceArtifact:
        updated = append_checkpoint(trace, stage_name, status, summary, artifacts, manual_review)
        self._store.save(session_id, updated)
        return updated

    def request_manual_review(
        self,
        session_id: str,
        trace: TraceArtifact,
        stage_name: str,
        summary: str,
        artifacts: dict[str, str] | None = None,
    ) -> TraceArtifact:
        return self.checkpoint(
            session_id,
            trace,
            stage_name=stage_name,
            status="manual_review",
            summary=summary,
            artifacts=artifacts,
            manual_review=True,
        )
