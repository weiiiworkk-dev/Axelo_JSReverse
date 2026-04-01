from __future__ import annotations

from axelo.models.trace import TraceArtifact


def latest_checkpoint(trace: TraceArtifact) -> tuple[str | None, str | None]:
    if not trace.checkpoints:
        return None, None
    checkpoint = trace.checkpoints[-1]
    return checkpoint.stage_name, checkpoint.status
