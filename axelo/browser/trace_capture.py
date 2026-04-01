from __future__ import annotations

import uuid
from datetime import datetime

from axelo.models.trace import TraceArtifact, WorkflowCheckpoint


def new_trace() -> TraceArtifact:
    return TraceArtifact(trace_id=str(uuid.uuid4())[:12], started_at=datetime.now(), updated_at=datetime.now())


def append_checkpoint(trace: TraceArtifact, stage_name: str, status: str, summary: str = "", artifacts: dict[str, str] | None = None, manual_review: bool = False) -> TraceArtifact:
    updated = trace.model_copy(deep=True)
    updated.checkpoints.append(
        WorkflowCheckpoint(
            checkpoint_id=str(uuid.uuid4())[:8],
            stage_name=stage_name,
            status=status,
            summary=summary,
            artifacts=artifacts or {},
            manual_review=manual_review,
        )
    )
    updated.updated_at = datetime.now()
    return updated
