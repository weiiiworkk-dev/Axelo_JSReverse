from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from axelo.ai.client import AIClient
from axelo.classifier.rules import DifficultyScore
from axelo.cost import CostBudget, CostGovernor, CostRecord
from axelo.models.analysis import AIHypothesis, AnalysisResult, DynamicAnalysis, StaticAnalysis
from axelo.models.codegen import GeneratedCode
from axelo.models.execution import ExecutionPlan
from axelo.models.pipeline import PipelineState
from axelo.models.target import TargetSite
from axelo.orchestrator.workflow_runtime import WorkflowRuntime


@dataclass
class MasterResult:
    session_id: str
    url: str
    difficulty: DifficultyScore | None = None
    analysis: AnalysisResult | None = None
    generated: GeneratedCode | None = None
    verified: bool = False
    cost: CostRecord | None = None
    output_dir: Path | None = None
    report_path: Path | None = None
    execution_plan: ExecutionPlan | None = None
    adapter_reused: bool = False
    route_label: str = ""
    reuse_hits: list[str] = field(default_factory=list)
    error: str | None = None
    completed: bool = False


@dataclass
class MasterRunContext:
    sid: str
    mode_name: str
    mode: object
    cost: CostRecord
    budget: CostBudget
    governor: CostGovernor
    result: MasterResult
    state: PipelineState
    workflow: WorkflowRuntime
    target: TargetSite
    runtime_policy: object
    session_dir: Path
    output_dir: Path
    memory_ctx: dict[str, object]
    adapter_candidate: object | None = None
    analysis: AnalysisResult | None = None
    generated: GeneratedCode | None = None
    verified: bool = False
    difficulty: DifficultyScore | None = None
    static_results: dict[str, StaticAnalysis] = field(default_factory=dict)
    bundle_hashes: list[str] = field(default_factory=list)
    dynamic: DynamicAnalysis | None = None
    hypothesis: AIHypothesis | None = None
    ai_client: AIClient | None = None
    analysis_cache_hit: bool = False
    family_match: object | None = None
    scan_report: object | None = None
