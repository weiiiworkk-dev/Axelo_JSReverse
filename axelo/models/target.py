from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from axelo.models.compliance import CompliancePolicy
from axelo.models.execution import ExecutionPlan
from axelo.models.session_state import SessionState
from axelo.models.site_profile import SiteProfile
from axelo.models.trace import TraceArtifact


class RequestCapture(BaseModel):
    """Captured network request/response pair."""

    url: str
    method: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: bytes | None = None
    response_status: int = 0
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: bytes | None = None
    timestamp: float = 0.0
    initiator: Literal["fetch", "xhr", "script", "navigation", "other"] = "other"
    call_stack: list[str] = Field(default_factory=list)
    is_target: bool = False
    token_fields: list[str] = Field(default_factory=list)


class BrowserProfile(BaseModel):
    """Browser fingerprint configuration."""

    user_agent: str = ""
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    extra_headers: dict[str, str] = Field(default_factory=dict)
    stealth: bool = True


class TargetSite(BaseModel):
    """Target site and run-scoped metadata."""

    url: str
    session_id: str
    interaction_goal: str
    created_at: datetime = Field(default_factory=datetime.now)
    browser_profile: BrowserProfile = Field(default_factory=BrowserProfile)
    captured_requests: list[RequestCapture] = Field(default_factory=list)
    target_requests: list[RequestCapture] = Field(default_factory=list)
    js_urls: list[str] = Field(default_factory=list)
    site_profile: SiteProfile = Field(default_factory=SiteProfile)
    compliance: CompliancePolicy = Field(default_factory=CompliancePolicy)
    session_state: SessionState = Field(default_factory=SessionState)
    trace: TraceArtifact = Field(default_factory=TraceArtifact)
    execution_plan: ExecutionPlan | None = None
    known_endpoint: str = ""
    antibot_type: str = "unknown"
    requires_login: bool | None = None
    output_format: str = "print"
    crawl_rate: str = "standard"
