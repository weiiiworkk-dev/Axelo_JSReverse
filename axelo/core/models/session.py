from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    INIT = "init"
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class SessionState(BaseModel):
    session_id: str
    target_url: str
    objective: str
    status: SessionStatus = SessionStatus.INIT
    history: list[dict[str, Any]] = Field(default_factory=list)
    agent_results: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    meta: dict[str, Any] = Field(default_factory=dict)

    def transition(self, new_status: SessionStatus, reason: str = "") -> None:
        self.history.append({
            "from": self.status.value,
            "to": new_status.value,
            "at": datetime.now().isoformat(),
            "reason": reason,
        })
        self.status = new_status
        self.updated_at = datetime.now()
