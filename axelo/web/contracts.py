from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat()


ThreadItemKind = Literal[
    "user_message",
    "router_message",
    "agent_activity_block",
    "deliverable_block",
    "checkpoint_message",
    "system_notice",
]

RunStatus = Literal["idle", "running", "blocked", "failed", "completed"]
RunPhase = Literal["intake", "planning", "running", "blocked", "completed", "failed"]
AgentStatus = Literal["idle", "running", "blocked", "failed", "completed"]
StepStatus = Literal["pending", "running", "completed", "blocked", "failed", "skipped"]
CheckpointStatus = Literal["waiting", "approved", "rejected", "expired"]
EventActorType = Literal["user", "router", "agent", "system"]


class ArtifactRef(BaseModel):
    artifact_id: str
    run_id: str
    title: str
    artifact_type: str
    status: str = "ready"
    uri: str = ""
    summary: str = ""
    created_at: str = Field(default_factory=now_iso)


class CheckpointRecord(BaseModel):
    checkpoint_id: str
    run_id: str
    question: str
    status: CheckpointStatus = "waiting"
    created_at: str = Field(default_factory=now_iso)
    resolved_at: str = ""
    resolution: str = ""


class PlanStepView(BaseModel):
    step_id: str
    title: str
    status: StepStatus = "pending"
    agent_id: str = ""
    note: str = ""
    updated_at: str = Field(default_factory=now_iso)


class AgentStateView(BaseModel):
    agent_id: str
    label: str
    status: AgentStatus = "idle"
    current_task: str = ""
    last_update: str = Field(default_factory=now_iso)


class ChatThreadItem(BaseModel):
    item_id: str
    session_id: str
    run_id: str = ""
    kind: ThreadItemKind
    created_at: str = Field(default_factory=now_iso)
    actor_type: EventActorType
    actor_id: str
    title: str = ""
    content: str = ""
    status: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class RunEvent(BaseModel):
    event_id: str
    session_id: str = ""
    run_id: str
    seq: int = 0
    ts: str = Field(default_factory=now_iso)
    kind: str
    actor_type: EventActorType = "system"
    actor_id: str = "system"
    phase: RunPhase = "running"
    payload: dict[str, Any] = Field(default_factory=dict)


class RunView(BaseModel):
    run_id: str
    session_id: str = ""
    status: RunStatus = "idle"
    phase: RunPhase = "planning"
    objective_text: str = ""
    phase_label: str = ""
    plan_steps: list[PlanStepView] = Field(default_factory=list)
    agents: list[AgentStateView] = Field(default_factory=list)
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    recent_event: str = ""
    connection_status: str = "offline"
    last_seq: int = 0


class SessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    status: str = "idle"
    site_key: str = ""
    site_code: str = ""
    url: str = ""
    latest_run_id: str = ""
    latest_run_status: str = "idle"
    is_legacy: bool = False


class SessionView(BaseModel):
    session_id: str
    title: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    status: str = "idle"
    intake_id: str = ""
    current_run_id: str = ""
    run_ids: list[str] = Field(default_factory=list)
    ready_to_run: bool = False
    thread_items: list[ChatThreadItem] = Field(default_factory=list)
