from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class RequirementSheet:
    target_url: str
    objective: str
    target_scope: str = ""
    fields: list[str] = field(default_factory=list)
    item_limit: int = 100
    auth_notes: str = ""
    constraints: str = ""
    output_expectation: str = ""
    created_at: str = field(default_factory=now_iso)

    def checklist(self) -> list[str]:
        return [
            f"Target URL: {self.target_url}",
            f"Objective: {self.objective}",
            f"Scope: {self.target_scope or 'default listing/search/detail flow'}",
            f"Fields: {', '.join(self.fields) if self.fields else 'auto-infer at runtime'}",
            f"Item limit: {self.item_limit}",
            f"Auth/Access: {self.auth_notes or 'no special auth requirement provided'}",
            f"Constraints: {self.constraints or 'standard crawl and reverse flow'}",
            f"Expected output: {self.output_expectation or 'crawler + reverse result + collected data + logs'}",
        ]

    def to_prompt(self) -> str:
        checklist = "\n".join(f"- {item}" for item in self.checklist())
        return (
            "Requirement checklist for this run:\n"
            f"{checklist}\n\n"
            "Plan and execute the crawling/reverse-engineering task based on this checklist."
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "target_url": self.target_url,
            "objective": self.objective,
            "target_scope": self.target_scope,
            "fields": list(self.fields),
            "item_limit": self.item_limit,
            "auth_notes": self.auth_notes,
            "constraints": self.constraints,
            "output_expectation": self.output_expectation,
            "created_at": self.created_at,
        }

class MissionOutcome(str, Enum):
    """Deprecated: use VerdictTier instead. Kept for backwards compatibility."""
    UNKNOWN = "unknown"
    FAILED = "failed"
    OPERATIONAL_SUCCESS = "operational_success"
    REPLAY_SUCCESS = "replay_success"
    MECHANISM_PARTIAL = "mechanism_partial"
    MECHANISM_VALIDATED = "mechanism_validated"


class VerdictTier(str, Enum):
    """Ordered verdict tiers for mission outcomes. Higher numeric value = better outcome."""
    FAILED              = "failed"               # -2: execution failed or no usable output
    EXECUTION_SUCCESS   = "execution_success"    #  1: code ran, no data guarantee
    DATA_SUCCESS        = "data_success"         #  2: data returned, fields found
    STRUCTURAL_SUCCESS  = "structural_success"   #  3: paths validated, schema confirmed
    OPERATIONAL_SUCCESS = "operational_success"  #  4: usable output, no mechanism required
    MECHANISM_SUCCESS   = "mechanism_success"    #  5: full mechanism understanding
    PARTIAL_SUCCESS     = "partial_success"      # -1: cross-dimensional partial
    INTAKE_COMPLETE     = "intake_complete"      #  0: pre-execution (not an execution verdict)


# Numeric rank for verdict comparison (higher = better outcome)
VERDICT_RANK: dict[str, int] = {
    VerdictTier.FAILED:              -2,
    VerdictTier.PARTIAL_SUCCESS:     -1,
    VerdictTier.INTAKE_COMPLETE:      0,
    VerdictTier.EXECUTION_SUCCESS:    1,
    VerdictTier.DATA_SUCCESS:         2,
    VerdictTier.STRUCTURAL_SUCCESS:   3,
    VerdictTier.OPERATIONAL_SUCCESS:  4,
    VerdictTier.MECHANISM_SUCCESS:    5,
}

# Backwards compat: map new tiers to old MissionOutcome values
TIER_TO_OUTCOME: dict[str, str] = {
    VerdictTier.FAILED:              MissionOutcome.FAILED.value,
    VerdictTier.EXECUTION_SUCCESS:   MissionOutcome.UNKNOWN.value,
    VerdictTier.DATA_SUCCESS:        MissionOutcome.OPERATIONAL_SUCCESS.value,
    VerdictTier.STRUCTURAL_SUCCESS:  MissionOutcome.REPLAY_SUCCESS.value,
    VerdictTier.OPERATIONAL_SUCCESS: MissionOutcome.OPERATIONAL_SUCCESS.value,
    VerdictTier.MECHANISM_SUCCESS:   MissionOutcome.MECHANISM_VALIDATED.value,
    VerdictTier.PARTIAL_SUCCESS:     MissionOutcome.MECHANISM_PARTIAL.value,
    VerdictTier.INTAKE_COMPLETE:     MissionOutcome.UNKNOWN.value,
}


@dataclass
class EngineRequest:
    prompt: str
    url: str = ""
    goal: str = ""
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    @property
    def effective_goal(self) -> str:
        return (self.goal or self.prompt).strip()


@dataclass
class TaskIntent:
    intent_type: str
    confidence: float
    reasoning: str = ""
    complexity: str = "medium"
    requires_browser: bool = False
    requires_stealth: bool = False


@dataclass
class EnginePlan:
    session_id: str
    summary: str
    intent: TaskIntent
    lines_of_inquiry: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)


@dataclass
class PreparedRun:
    request: EngineRequest
    plan: EnginePlan
    session_id: str
    session_dir: str
    principal_state: "PrincipalAgentState | None" = None
    mission_brief: "MissionBrief | None" = None
    contract: "Any | None" = None  # MissionContract, imported lazily to avoid circular deps


@dataclass
class MissionBrief:
    title: str
    summary: str
    lines_of_inquiry: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)


@dataclass
class NextActionSpec:
    objective_id: str
    objective: str
    capability: str
    reason: str
    needed_evidence: list[str] = field(default_factory=list)
    budget_weight: float = 1.0
    created_at: str = field(default_factory=now_iso)


@dataclass
class AgentReport:
    run_id: str
    objective_id: str
    objective: str
    capability: str
    agent_role: str
    success: bool
    summary: str
    claims: list[str] = field(default_factory=list)
    counterevidence: list[str] = field(default_factory=list)
    evidence: list["EvidenceRecord"] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    tool_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommended_questions: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    created_at: str = field(default_factory=now_iso)


@dataclass
class EvidenceRecord:
    evidence_id: str
    kind: str
    source_task: str
    summary: str
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)


@dataclass
class EvidenceLink:
    link_id: str
    relation: str
    source_id: str
    target_id: str
    summary: str = ""
    confidence: float = 0.0
    created_at: str = field(default_factory=now_iso)


@dataclass
class EvidenceImpact:
    impact_id: str
    evidence_id: str
    hypothesis_id: str
    direction: str
    strength: float
    why: str
    created_at: str = field(default_factory=now_iso)


@dataclass
class EvidenceGraph:
    nodes: list[EvidenceRecord] = field(default_factory=list)
    links: list[EvidenceLink] = field(default_factory=list)
    impacts: list[EvidenceImpact] = field(default_factory=list)
    request_token_map: dict[str, list[str]] = field(default_factory=dict)
    token_sources: dict[str, list[str]] = field(default_factory=dict)
    hypothesis_support: dict[str, list[str]] = field(default_factory=dict)
    hypothesis_refute: dict[str, list[str]] = field(default_factory=dict)
    dominant_hypothesis_id: str = ""
    coverage: dict[str, float] = field(
        default_factory=lambda: {
            "acquisition": 0.0,
            "protocol": 0.0,
            "reverse": 0.0,
            "runtime": 0.0,
            "schema": 0.0,
            "extraction": 0.0,
            "build": 0.0,
            "verify": 0.0,
        }
    )
    updated_at: str = field(default_factory=now_iso)


@dataclass
class HypothesisRecord:
    hypothesis_id: str
    statement: str
    mechanism_class: str = ""
    confidence: float = 0.0
    prior: float = 0.0
    posterior: float = 0.0
    support_score: float = 0.0
    refute_score: float = 0.0
    status: str = "active"
    supporting_evidence: list[str] = field(default_factory=list)
    refuting_evidence: list[str] = field(default_factory=list)
    unresolved_contradictions: list[str] = field(default_factory=list)
    next_probe: str = ""
    created_at: str = field(default_factory=now_iso)


@dataclass
class AgendaRecord:
    item_id: str
    label: str
    owner: str
    status: str = "pending"
    rationale: str = ""
    depends_on: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class BranchRecord:
    branch_id: str
    label: str
    status: str = "active"
    score: float = 0.5
    budget_weight: float = 1.0
    spent_budget: float = 0.0
    parent_branch_id: str = ""
    rationale: str = ""
    task_ids: list[str] = field(default_factory=list)
    focus: str = ""
    updated_at: str = field(default_factory=now_iso)


@dataclass
class MissionState:
    session_id: str
    target_url: str
    objective: str
    phase: str = "planned"
    status: str = "active"
    outcome: str = MissionOutcome.UNKNOWN.value
    verdict_tier: str = VerdictTier.INTAKE_COMPLETE.value  # new: fine-grained verdict
    current_focus: str = ""
    current_uncertainty: str = ""
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    mechanism_required: bool = True
    has_unresolved_agenda: bool = False  # set by AgendaReconciler before verdict
    budget_total: float = 1.0
    budget_spent: float = 0.0
    updated_at: str = field(default_factory=now_iso)


@dataclass
class TrustAssessment:
    score: float = 0.0
    level: str = "low"
    summary: str = ""
    execution_score: float = 0.0
    execution_level: str = "low"
    execution_summary: str = ""
    mechanism_score: float = 0.0
    mechanism_level: str = "low"
    mechanism_summary: str = ""
    blockers: list[str] = field(default_factory=list)
    indicators: dict[str, float] = field(default_factory=dict)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class MechanismAssessment:
    verdict: str = "unknown"
    summary: str = ""
    dominant_hypothesis_id: str = ""
    blocking_conditions: list[str] = field(default_factory=list)
    non_blocking_gaps: list[str] = field(default_factory=list)
    explained_dimensions: dict[str, bool] = field(default_factory=dict)
    unresolved_dimensions: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class PrincipalAgentState:
    mission: MissionState
    agenda: list[AgendaRecord] = field(default_factory=list)
    hypotheses: list[HypothesisRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    evidence_graph: EvidenceGraph = field(default_factory=EvidenceGraph)
    branches: list[BranchRecord] = field(default_factory=list)
    active_branch_id: str = "main"
    open_questions: list[str] = field(default_factory=list)
    worklog: list[str] = field(default_factory=list)
    trust: TrustAssessment = field(default_factory=TrustAssessment)
    mechanism: MechanismAssessment = field(default_factory=MechanismAssessment)
    cognition_summary: str = ""
    last_review_reason: str = ""
    next_action_hint: str = ""
    evidence_delta: str = ""
    objective_attempts: dict[str, int] = field(default_factory=dict)
    objective_stalls: dict[str, int] = field(default_factory=dict)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class AgentExecutionResult:
    task_id: str
    tool_name: str
    agent_role: str
    success: bool
    status: str
    duration_seconds: float
    output_keys: list[str] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=now_iso)


@dataclass
class ArtifactRecord:
    category: str
    name: str
    path: str
    description: str


@dataclass
class ArtifactBundle:
    session_id: str
    root_dir: str
    index_path: str
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    summary: str = ""


@dataclass
class SemanticCheck:
    field_name: str
    data_type_correct: bool = False
    range_plausible: bool = False
    pattern_match: bool = False
    semantic_verdict: str = "unknown"   # "validated" | "suspicious" | "failed"
    validation_notes: str = ""


@dataclass
class VerificationRecord:
    """Extended evidence record capturing all three verify layers."""
    evidence_id: str
    kind: str = "verify"
    source_task: str = ""
    summary: str = ""
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    # Layer 1: Execution verification
    execution_verdict: str = "unknown"      # "pass" | "fail" | "error"
    http_status: int = 0
    no_crash: bool = False
    duration_seconds: float = 0.0

    # Layer 2: Structural verification
    structural_verdict: str = "unknown"     # "pass" | "partial" | "fail"
    fields_present: list[str] = field(default_factory=list)
    fields_missing: list[str] = field(default_factory=list)
    record_count: int = 0
    target_record_count: int = 0
    schema_match: bool = False

    # Layer 3: Semantic verification
    semantic_verdict: str = "unknown"       # "validated" | "suspicious" | "failed"
    semantic_checks: list[SemanticCheck] = field(default_factory=list)

    # Rolled-up
    overall_verdict: str = "unknown"
    fallback_strategy: str = "none"         # "none" | "page_extract" | "api_intercept" | "bridge" | "manual"
    mechanism_closure: bool = False         # True only if no mechanism blockers remain
    stability_level: str = "unknown"        # "stable" | "fragile" | "unknown"

    def __post_init__(self) -> None:
        """Sync typed layer fields into the details dict so evidence_coverage() can read them."""
        self.details.setdefault("execution_verdict", self.execution_verdict)
        self.details.setdefault("structural_verdict", self.structural_verdict)
        self.details.setdefault("semantic_verdict", self.semantic_verdict)
        self.details.setdefault("fallback_strategy", self.fallback_strategy)
        self.details.setdefault("mechanism_closure", self.mechanism_closure)
        self.details.setdefault("record_count", self.record_count)
        self.details.setdefault("target_record_count", self.target_record_count)
        self.details.setdefault("fields_present", self.fields_present)
        self.details.setdefault("fields_missing", self.fields_missing)


@dataclass
class VerdictChain:
    """Auditable record of how the final verdict was determined."""
    tier: str                                # VerdictTier value
    status: str                              # "success" | "partial" | "failed"
    conditions_met: list[str] = field(default_factory=list)
    conditions_failed: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    agenda_reconciliation: list[str] = field(default_factory=list)
    field_verdict: dict[str, str] = field(default_factory=dict)     # field_name → validation_status
    coverage_snapshot: dict[str, float] = field(default_factory=dict)
    mechanism_assessment_summary: str = ""
    mechanism_blockers: list[str] = field(default_factory=list)
    assessed_at: str = field(default_factory=now_iso)


@dataclass
class EngineRunResult:
    session_id: str
    success: bool
    summary: str
    plan: EnginePlan
    agent_results: list[AgentExecutionResult]
    artifact_bundle: ArtifactBundle
    principal_state: PrincipalAgentState | None = None
    mission_brief: MissionBrief | None = None
    execution_success: bool = False
    verdict_chain: VerdictChain | None = None
    created_at: str = field(default_factory=now_iso)
