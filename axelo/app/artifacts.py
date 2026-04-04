from __future__ import annotations

from dataclasses import dataclass, field

from axelo.classifier.rules import DifficultyScore
from axelo.models.analysis import AIHypothesis, AnalysisResult, DynamicAnalysis, StaticAnalysis
from axelo.models.bundle import JSBundle
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite


@dataclass
class DiscoveryArtifacts:
    target: TargetSite
    bundles: list[JSBundle] = field(default_factory=list)
    bundle_hashes: list[str] = field(default_factory=list)
    static_results: dict[str, StaticAnalysis] = field(default_factory=dict)
    analysis_cache_hit: bool = False


@dataclass
class AnalysisArtifacts:
    difficulty: DifficultyScore | None = None
    dynamic: DynamicAnalysis | None = None
    family_match: object | None = None
    analysis: AnalysisResult | None = None
    hypothesis: AIHypothesis | None = None
    scan_report: object | None = None


@dataclass
class DeliveryArtifacts:
    generated: GeneratedCode | None = None
    verification: object | None = None
    verification_analysis: object | None = None
    verified: bool = False
