from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SignatureSpec(BaseModel):
    """Machine-executable summary of the inferred request-signing contract."""

    algorithm_id: str = "unknown"
    canonical_steps: list[str] = Field(default_factory=list)
    input_fields: list[str] = Field(default_factory=list)
    output_fields: dict[str, str] = Field(default_factory=dict)
    browser_dependencies: list[str] = Field(default_factory=list)
    replay_requirements: list[str] = Field(default_factory=list)
    normalization_rules: list[str] = Field(default_factory=list)
    bridge_targets: list[str] = Field(default_factory=list)
    preferred_bridge_target: str | None = None
    topology_summary: list[str] = Field(default_factory=list)
    codegen_strategy: Literal["python_reconstruct", "js_bridge", "manual_required"] = "js_bridge"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
