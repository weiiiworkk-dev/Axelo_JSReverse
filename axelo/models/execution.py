from __future__ import annotations

from datetime import datetime
from enum import Enum
import uuid

from pydantic import BaseModel, Field


class ExecutionTier(str, Enum):
    ADAPTER_REUSE = "adapter_reuse"
    BROWSER_LIGHT = "browser_light"
    BROWSER_FULL = "browser_full"
    MANUAL_REVIEW = "manual_review"


class VerificationMode(str, Enum):
    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


class ExecutionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = Field(default_factory=datetime.now)
    tier: ExecutionTier = ExecutionTier.BROWSER_FULL
    verification_mode: VerificationMode = VerificationMode.STANDARD
    requires_browser: bool = True
    requires_dynamic_analysis: bool = True
    requires_ai: bool = True
    adapter_key: str = ""
    adapter_hit: bool = False
    skip_fetch_and_static: bool = False
    skip_codegen: bool = False
    should_persist_adapter: bool = True
    enable_trace_capture: bool = True
    enable_action_flow: bool = True
    enable_target_confirmation: bool = True
    max_crawl_retries: int = Field(default=1, ge=1, le=5)
    max_session_rotations: int = Field(default=1, ge=1, le=5)
    estimated_cost: str = "medium"
    reasons: list[str] = Field(default_factory=list)
    degradation_notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

