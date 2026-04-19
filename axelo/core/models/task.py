from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    agent: str                          # "recon" | "browser" | "analysis" | ...
    objective: str                      # natural language description passed to agent
    depends_on: list[str] = Field(default_factory=list)  # agent names this depends on
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.attempt += 1
        self.started_at = datetime.now()

    def mark_complete(self, result: Any) -> None:
        self.status = TaskStatus.COMPLETE
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()


class TaskGraph(BaseModel):
    tasks: list[SubTask] = Field(default_factory=list)

    def ready_tasks(self) -> list[SubTask]:
        """Return all PENDING tasks whose dependencies are all COMPLETE."""
        completed_agents = {
            t.agent for t in self.tasks if t.status == TaskStatus.COMPLETE
        }
        return [
            t for t in self.tasks
            if t.status == TaskStatus.PENDING
            and all(dep in completed_agents for dep in t.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETE, TaskStatus.SKIPPED) for t in self.tasks)

    def has_failure(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks)

    def get_by_agent(self, agent: str) -> SubTask | None:
        return next((t for t in self.tasks if t.agent == agent), None)
