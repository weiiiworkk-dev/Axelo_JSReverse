from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


OutputMode = Literal["standalone", "bridge"]


class GeneratedCode(BaseModel):
    """Generated crawler artifacts for one run."""

    session_id: str
    output_mode: OutputMode
    generated_at: datetime = Field(default_factory=datetime.now)
    crawler_script_path: Path | None = None
    crawler_deps: list[str] = Field(default_factory=list)
    bridge_server_path: Path | None = None
    bridge_port: int = 8721
    manifest_path: Path | None = None
    verified: bool = False
    verification_notes: str = ""
    session_state_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}
