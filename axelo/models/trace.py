from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowCheckpoint(BaseModel):
    checkpoint_id: str
    stage_name: str
    status: str
    summary: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)
    manual_review: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class TraceArtifact(BaseModel):
    trace_id: str = ""
    trace_zip_path: str = ""
    network_log_path: str = ""
    checkpoints: list[WorkflowCheckpoint] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
