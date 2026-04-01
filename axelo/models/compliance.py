from __future__ import annotations

from pydantic import BaseModel, Field


class CompliancePolicy(BaseModel):
    """Guardrails for automated execution and verification."""

    mode: str = "guarded"
    require_manual_for_extreme: bool = True
    allow_live_verification: bool = True
    allow_action_flow: bool = True
    max_auto_verify_retries: int = Field(default=2, ge=0, le=5)
    stability_runs: int = Field(default=2, ge=1, le=5)
    notes: list[str] = Field(default_factory=list)
