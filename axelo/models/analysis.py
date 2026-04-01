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


class HookIntercept(BaseModel):
    """One observed hook invocation captured during dynamic analysis."""

    api_name: str
    args_repr: str
    return_repr: str
    stack_trace: list[str] = Field(default_factory=list)
    timestamp: float = 0.0
    sequence: int = 0


class DynamicAnalysis(BaseModel):
    """Runtime analysis results inferred from browser hooks."""

    bundle_id: str
    hook_intercepts: list[HookIntercept] = Field(default_factory=list)
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
    codegen_strategy: Literal["python_reconstruct", "js_bridge"] = "js_bridge"
    python_feasibility: float = 0.0
    confidence: float = 0.0
    notes: str = ""
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
