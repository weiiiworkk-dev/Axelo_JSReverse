from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from axelo.models.signature import SignatureSpec


class FunctionSignature(BaseModel):
    """Static function metadata extracted from AST analysis."""

    func_id: str
    name: str | None = None
    source_file: str = ""
    line: int = 0
    col: int = 0
    params: list[str] = Field(default_factory=list)
    is_async: bool = False
    calls: list[str] = Field(default_factory=list)
    called_by: list[str] = Field(default_factory=list)
    cyclomatic_complexity: int = 1
    raw_source: str = ""


TokenType = Literal[
    "hmac",
    "sha256",
    "md5",
    "aes",
    "timestamp",
    "nonce",
    "uuid",
    "fingerprint",
    "base64",
    "custom",
    "rsa",
    "ecdsa",
    "sha1",
    "sha512",
    "hmac_sha256",
    "aes_gcm",
    "aes_cbc",
    "des",
    "rc4",
    "unknown",
]


class TokenCandidate(BaseModel):
    """Candidate function that appears to produce a signing field."""

    func_id: str
    token_type: TokenType = "unknown"
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)
    request_field: str | None = None
    source_snippet: str = ""


class StaticAnalysis(BaseModel):
    """Bundle-level static analysis output."""

    bundle_id: str
    entry_points: list[str] = Field(default_factory=list)
    function_map: dict[str, FunctionSignature] = Field(default_factory=dict)
    token_candidates: list[TokenCandidate] = Field(default_factory=list)
    crypto_imports: list[str] = Field(default_factory=list)
    env_access: list[str] = Field(default_factory=list)
    string_constants: list[str] = Field(default_factory=list)
    call_graph_path: str | None = None
    error_messages: list[str] = Field(default_factory=list)


class HookIntercept(BaseModel):
    """One observed hook invocation captured during dynamic analysis."""

    api_name: str
    args_repr: str
    return_repr: str
    stack_trace: list[str] = Field(default_factory=list)
    timestamp: float = 0.0
    sequence: int = 0


class TaintSink(BaseModel):
    """One tainted request sink observed in the page."""

    request_id: str = ""
    sink_field: str = ""
    sink_kind: Literal["header", "body", "query", "beacon", "unknown"] = "unknown"
    request_url: str = ""
    request_method: str = ""


class TaintEvent(BaseModel):
    """Structured taint event emitted by the browser runtime."""

    event_type: Literal["source", "transform", "sink"]
    api_name: str
    taint_ids: list[str] = Field(default_factory=list)
    parent_taint_ids: list[str] = Field(default_factory=list)
    sequence: int = 0
    timestamp: float = 0.0
    stack_trace: list[str] = Field(default_factory=list)
    value_preview: str = ""
    sink: TaintSink | None = None


class BridgeTargetCandidate(BaseModel):
    """Callable browser-side function candidate derived from taint topology."""

    name: str
    global_path: str = ""
    owner_path: str = ""
    resolver_source: str = ""
    score: float = 0.0
    callable: bool = False
    sink_field: str = ""
    evidence_frames: list[str] = Field(default_factory=list)


class TaintTopology(BaseModel):
    """One taint chain ending at a request sink."""

    sink_field: str
    sink_kind: Literal["header", "body", "query", "beacon", "unknown"] = "unknown"
    request_id: str = ""
    request_url: str = ""
    request_method: str = ""
    ordered_steps: list[str] = Field(default_factory=list)
    taint_ids: list[str] = Field(default_factory=list)
    entrypoint_candidates: list[BridgeTargetCandidate] = Field(default_factory=list)
    confidence: float = 0.0


class DynamicAnalysis(BaseModel):
    """Runtime analysis results inferred from browser hooks."""

    bundle_id: str
    hook_intercepts: list[HookIntercept] = Field(default_factory=list)
    taint_events: list[TaintEvent] = Field(default_factory=list)
    topologies: list[TaintTopology] = Field(default_factory=list)
    bridge_candidates: list[BridgeTargetCandidate] = Field(default_factory=list)
    topology_summary: list[str] = Field(default_factory=list)
    confirmed_generators: list[str] = Field(default_factory=list)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    crypto_primitives: list[str] = Field(default_factory=list)


class AIHypothesis(BaseModel):
    """Natural-language reverse-engineering hypothesis from AI analysis."""

    algorithm_description: str
    generator_func_ids: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    family_id: str = "unknown"
    codegen_strategy: Literal["python_reconstruct", "js_bridge"] = "js_bridge"
    python_feasibility: float = 0.0
    confidence: float = 0.0
    notes: str = ""
    template_name: str = ""
    secret_candidate: str = ""
    signature_spec: SignatureSpec | None = None


class AnalysisResult(BaseModel):
    """Cross-stage analysis summary for one run."""

    session_id: str
    static: dict[str, StaticAnalysis] = Field(default_factory=dict)
    dynamic: DynamicAnalysis | None = None
    ai_hypothesis: AIHypothesis | None = None
    signature_spec: SignatureSpec | None = None
    overall_confidence: float = 0.0
    ready_for_codegen: bool = False
    manual_review_required: bool = False
    signature_family: str = "unknown"
    analysis_notes: str = ""
