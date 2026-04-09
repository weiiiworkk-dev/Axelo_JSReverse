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
    ai_mode: str = "full"
    route_label: str = "full_ai_unknown_family"
    cost_strategy: str = "balanced"
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
    max_bundles: int = Field(default=6, ge=1, le=20)
    max_bundle_size_kb: int = Field(default=512, ge=64, le=4096)
    max_total_bundle_kb: int = Field(default=1600, ge=128, le=16384)
    estimated_cost: str = "medium"
    estimated_cost_range: str = "$0.40-$0.90"
    reasons: list[str] = Field(default_factory=list)
    degradation_notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Warmup navigation before main crawl
    warmup_enabled: bool = False
    warmup_url: str | None = None

    # Universal challenge resolution
    challenge_resolution_enabled: bool = True
    challenge_resolution_timeout: float | None = None   # None → use config default
    challenge_fail_policy: str = "human_in_loop"        # "warn" | "abort" | "human_in_loop"
    max_challenge_retries: int = 2
