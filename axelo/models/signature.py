from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SignatureSpec(BaseModel):
    """Machine-executable summary of the inferred request-signing contract."""

    algorithm_id: str = "unknown"
    family_id: str = "unknown"
    canonical_steps: list[str] = Field(default_factory=list)
    input_fields: list[str] = Field(default_factory=list)
    signing_inputs: list[str] = Field(default_factory=list)
    output_fields: dict[str, str] = Field(default_factory=dict)
    signing_outputs: dict[str, str] = Field(default_factory=dict)
    browser_dependencies: list[str] = Field(default_factory=list)
    replay_requirements: list[str] = Field(default_factory=list)
    normalization_rules: list[str] = Field(default_factory=list)
    transport_profile: dict[str, str] = Field(default_factory=dict)
    header_policy: dict[str, list[str]] = Field(default_factory=dict)
    cookie_policy: dict[str, list[str] | str] = Field(default_factory=dict)
    bridge_targets: list[str] = Field(default_factory=list)
    preferred_bridge_target: str | None = None
    bridge_mode: str = "none"
    extractor_binding: dict[str, str] = Field(default_factory=dict)
    stability_level: str = "standard"
    topology_summary: list[str] = Field(default_factory=list)
    codegen_strategy: Literal["python_reconstruct", "js_bridge", "manual_required"] = "js_bridge"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _normalize_v2_fields(self) -> "SignatureSpec":
        if not self.signing_inputs:
            self.signing_inputs = list(self.input_fields)
        if not self.input_fields:
            self.input_fields = list(self.signing_inputs)
        if not self.signing_outputs:
            self.signing_outputs = dict(self.output_fields)
        if not self.output_fields:
            self.output_fields = dict(self.signing_outputs)
        if self.family_id == "unknown" and self.algorithm_id:
            self.family_id = self.algorithm_id
        return self
