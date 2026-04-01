from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class SessionState(BaseModel):
    """Persisted browser and session metadata for re-use across runs."""

    session_key: str = ""
    domain: str = ""
    storage_state_path: str = ""
    cookies: list[dict] = Field(default_factory=list)
    local_storage: dict[str, str] = Field(default_factory=dict)
    session_headers: dict[str, str] = Field(default_factory=dict)
    health_score: float = Field(default=1.0, ge=0.0, le=1.0)
    reuse_count: int = Field(default=0, ge=0)
    blocked: bool = False
    blocked_reason: str = ""
    last_status_code: int | None = None
    last_error: str = ""
    manual_review_required: bool = False
    consecutive_failures: int = Field(default=0, ge=0)
    cooldown_until: datetime | None = None
    last_used_at: datetime | None = None
    updated_at: datetime = Field(default_factory=datetime.now)
