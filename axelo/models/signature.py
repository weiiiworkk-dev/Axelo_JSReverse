from __future__ import annotations

from typing import Any, Literal

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
    signature_fields: dict[str, str] = Field(default_factory=dict)
    fingerprint_fields: dict[str, str] = Field(default_factory=dict)
    runtime_token_fields: dict[str, str] = Field(default_factory=dict)
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
    codegen_strategy: Literal["python_reconstruct", "js_bridge", "observed_replay", "manual_required"] = "js_bridge"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @staticmethod
    def _dedupe_casefold_list(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in values or []:
            text = str(item or "").strip()
            if not text:
                continue
            marker = text.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(text)
        return deduped

    @staticmethod
    def _dedupe_casefold_map(mapping: dict[str, Any]) -> dict[str, Any]:
        deduped: dict[str, Any] = {}
        index: dict[str, str] = {}
        for key, value in (mapping or {}).items():
            text = str(key or "").strip()
            if not text:
                continue
            marker = text.casefold()
            if marker not in index:
                index[marker] = text
                deduped[text] = value
                continue
            existing_key = index[marker]
            existing_value = deduped.get(existing_key)
            if existing_value in (None, "", [], {}) and value not in (None, "", [], {}):
                deduped[existing_key] = value
        return deduped

    @model_validator(mode="after")
    def _normalize_v2_fields(self) -> "SignatureSpec":
        self.canonical_steps = self._dedupe_casefold_list(self.canonical_steps)
        self.input_fields = self._dedupe_casefold_list(self.input_fields)
        self.signing_inputs = self._dedupe_casefold_list(self.signing_inputs)
        self.browser_dependencies = self._dedupe_casefold_list(self.browser_dependencies)
        self.replay_requirements = self._dedupe_casefold_list(self.replay_requirements)
        self.normalization_rules = self._dedupe_casefold_list(self.normalization_rules)
        self.bridge_targets = self._dedupe_casefold_list(self.bridge_targets)
        self.topology_summary = self._dedupe_casefold_list(self.topology_summary)
        self.output_fields = self._dedupe_casefold_map(self.output_fields)
        self.signing_outputs = self._dedupe_casefold_map(self.signing_outputs)
        self.signature_fields = self._dedupe_casefold_map(self.signature_fields)
        self.fingerprint_fields = self._dedupe_casefold_map(self.fingerprint_fields)
        self.runtime_token_fields = self._dedupe_casefold_map(self.runtime_token_fields)
        self.extractor_binding = self._dedupe_casefold_map(self.extractor_binding)
        if not self.signing_inputs:
            self.signing_inputs = list(self.input_fields)
        if not self.input_fields:
            self.input_fields = list(self.signing_inputs)
        if not self.signing_outputs:
            self.signing_outputs = dict(self.output_fields)
        if not self.output_fields:
            self.output_fields = dict(self.signing_outputs)
        if not self.signature_fields:
            self.signature_fields = dict(self.signing_outputs)
        if not self.signing_outputs:
            self.signing_outputs = dict(self.signature_fields)
        if not self.output_fields:
            combined = {}
            combined.update(self.signature_fields)
            combined.update(self.runtime_token_fields)
            combined.update(self.fingerprint_fields)
            self.output_fields = combined
        if self.header_policy:
            self.header_policy = {
                str(key): self._dedupe_casefold_list(value if isinstance(value, list) else [])
                for key, value in self.header_policy.items()
            }
        if self.cookie_policy:
            normalized_cookie_policy: dict[str, list[str] | str] = {}
            for key, value in self.cookie_policy.items():
                if isinstance(value, list):
                    normalized_cookie_policy[str(key)] = self._dedupe_casefold_list(value)
                else:
                    normalized_cookie_policy[str(key)] = str(value)
            self.cookie_policy = normalized_cookie_policy
        if self.family_id == "unknown" and self.algorithm_id:
            self.family_id = self.algorithm_id
        return self
