from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BrowserActionType(str, Enum):
    NAVIGATE = "navigate"
    WAIT = "wait"
    CLICK = "click"
    TYPE = "type"
    PRESS = "press"
    SCREENSHOT = "screenshot"
    EVALUATE = "evaluate"


class BrowserAction(BaseModel):
    action_type: BrowserActionType
    description: str = ""
    url: str = ""
    selector: str = ""
    text: str = ""
    key: str = ""
    script: str = ""
    duration_ms: int = Field(default=0, ge=0)
    optional: bool = False


class SiteProfile(BaseModel):
    domain: str = ""
    difficulty_hint: str = "unknown"
    login_url: str = ""
    extraction_hints: list[str] = Field(default_factory=list)
    action_flow: list[BrowserAction] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
