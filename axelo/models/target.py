from __future__ import annotations

from datetime import datetime
from typing import Literal

import hashlib

from pydantic import BaseModel, Field, field_serializer

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

    @field_serializer("request_body", "response_body", when_used="json")
    def _serialize_bytes_preview(self, value: bytes | None) -> str | None:
        if value is None:
            return None
        if not value:
            return ""
        preview = value[:4096]
        if b"\x00" in preview:
            return f"<binary {len(value)} bytes sha256={hashlib.sha256(value).hexdigest()[:16]}>"
        try:
            text = preview.decode("utf-8")
            suffix = "… [truncated]" if len(value) > len(preview) else ""
            return text + suffix
        except UnicodeDecodeError:
            text = preview.decode("utf-8", errors="replace")
            non_printable = sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t")
            if non_printable > max(8, len(text) // 20):
                return f"<binary {len(value)} bytes sha256={hashlib.sha256(value).hexdigest()[:16]}>"
            suffix = "… [truncated]" if len(value) > len(preview) else ""
            return text + suffix


class BatterySimulation(BaseModel):
    enabled: bool = True
    charging: bool = True
    charging_time: float = Field(default=0.0, ge=0.0)
    discharging_time: float | None = Field(default=None, ge=0.0)
    level: float = Field(default=1.0, ge=0.0, le=1.0)


class NetworkInformationSimulation(BaseModel):
    effective_type: str = "4g"
    rtt: int = Field(default=50, ge=1)
    downlink: float = Field(default=10.0, ge=0.1)
    save_data: bool = False


class MediaSimulation(BaseModel):
    enabled: bool = True
    pointer: str = "fine"
    hover: str = "hover"
    any_pointer: str = "fine"
    any_hover: str = "hover"
    hardware_concurrency: int = Field(default=8, ge=1)
    device_memory: int = Field(default=8, ge=1)
    max_touch_points: int = Field(default=0, ge=0)
    connection: NetworkInformationSimulation = Field(default_factory=NetworkInformationSimulation)


class WebGLSimulation(BaseModel):
    enabled: bool = True
    minimum_parameters: dict[str, int | float | list[int] | list[float]] = Field(
        default_factory=lambda: {
            "ALIASED_LINE_WIDTH_RANGE": [1, 1],
            "ALIASED_POINT_SIZE_RANGE": [1, 1],
            "MAX_COMBINED_TEXTURE_IMAGE_UNITS": 8,
            "MAX_CUBE_MAP_TEXTURE_SIZE": 1024,
            "MAX_FRAGMENT_UNIFORM_VECTORS": 16,
            "MAX_RENDERBUFFER_SIZE": 1024,
            "MAX_TEXTURE_IMAGE_UNITS": 8,
            "MAX_TEXTURE_SIZE": 2048,
            "MAX_VARYING_VECTORS": 8,
            "MAX_VERTEX_ATTRIBS": 8,
            "MAX_VERTEX_TEXTURE_IMAGE_UNITS": 0,
            "MAX_VERTEX_UNIFORM_VECTORS": 128,
        }
    )


class EnvironmentSimulation(BaseModel):
    enabled: bool = True
    profile_name: str = "desktop"
    color_scheme: str = "light"
    reduced_motion: str = "no-preference"
    device_scale_factor: float = Field(default=1.0, ge=0.5)
    has_touch: bool = False
    is_mobile: bool = False
    battery: BatterySimulation = Field(default_factory=BatterySimulation)
    media: MediaSimulation = Field(default_factory=MediaSimulation)
    webgl: WebGLSimulation = Field(default_factory=WebGLSimulation)


class PointerPathSimulation(BaseModel):
    default_seed: int = Field(default=1337, ge=1)
    sample_rate_hz: int = Field(default=60, ge=1)
    duration_ms: int = Field(default=1200, ge=16)
    jitter_px: float = Field(default=1.25, ge=0.0)
    curvature: float = Field(default=0.18, ge=0.0)
    hover_pause_ms: int = Field(default=0, ge=0)


class InteractionSimulation(BaseModel):
    enabled: bool = True
    profile_name: str = "synthetic_performance"
    mode: str = "playwright_mouse"
    high_frequency_dispatch: bool = False
    pointer: PointerPathSimulation = Field(default_factory=PointerPathSimulation)


class BrowserProfile(BaseModel):
    """Browser fingerprint configuration."""

    user_agent: str = ""
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    extra_headers: dict[str, str] = Field(default_factory=dict)
    environment_simulation: EnvironmentSimulation = Field(default_factory=EnvironmentSimulation)
    interaction_simulation: InteractionSimulation = Field(default_factory=InteractionSimulation)


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
    target_hint: str = ""
    use_case: str = "research"
    authorization_status: str = "pending"
    replay_mode: str = "discover_only"
    known_endpoint: str = ""
    antibot_type: str = "unknown"
    requires_login: bool | None = None
    output_format: str = "print"
    crawl_rate: str = "standard"
