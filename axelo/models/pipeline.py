from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    APPROVE_STAGE = "approve_stage"
    SELECT_OPTION = "select_option"
    EDIT_ARTIFACT = "edit_artifact"
    OVERRIDE_HYPOTHESIS = "override_hypothesis"
    CONFIRM_TARGET = "confirm_target"
    MANUAL_REVIEW = "manual_review"


class Decision(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    stage: str
    decision_type: DecisionType
    prompt: str
    options: list[str] | None = None
    artifact_path: Path | None = None
    context_summary: str = ""
    default: str | None = None
    outcome: str | None = None
    rationale: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class StageRecord(BaseModel):
    stage_name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    decisions: list[Decision] = Field(default_factory=list)
    error: str | None = None


class PipelineState(BaseModel):
    session_id: str
    mode: str = "interactive"
    current_stage_index: int = 0
    stages: list[StageRecord] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    completed: bool = False
    error: str | None = None
    workflow_status: str = "running"
    manual_review_reason: str = ""
    execution_plan: dict[str, Any] = Field(default_factory=dict)

    def get_stage(self, name: str) -> StageRecord | None:
        for stage in self.stages:
            if stage.stage_name == name:
                return stage
        return None

    def set_artifact(self, key: str, path: Path) -> None:
        self.artifacts[key] = str(path)

    def get_artifact(self, key: str) -> Path | None:
        value = self.artifacts.get(key)
        return Path(value) if value else None


class StageResult(BaseModel):
    stage_name: str
    success: bool
    artifacts: dict[str, Path | None] = Field(default_factory=dict)
    decisions: list[Decision] = Field(default_factory=list)
    summary: str = ""
    error: str | None = None
    duration_seconds: float = 0.0
    next_input: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
