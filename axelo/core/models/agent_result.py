from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import uuid


class ResultStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class AgentResult(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent: str
    status: ResultStatus
    data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)  # list of artifact file paths written
    error: str | None = None
    duration_ms: float | None = None
    produced_at: datetime = Field(default_factory=datetime.now)
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ResultStatus.SUCCESS
