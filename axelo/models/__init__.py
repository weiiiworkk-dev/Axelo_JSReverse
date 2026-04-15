from .analysis import (
    AIHypothesis,
    AnalysisResult,
    BridgeTargetCandidate,
    DynamicAnalysis,
    FunctionSignature,
    HookIntercept,
    StaticAnalysis,
    TaintEvent,
    TaintSink,
    TaintTopology,
    TokenCandidate,
)
from .bundle import DeobfuscationResult, JSBundle
from .codegen import GeneratedCode
from .compliance import CompliancePolicy
from .contracts import (
    AdapterPackage,
    CapabilityProfile,
    CaptureIntent,
    DatasetContract,
    EvidenceBundle,
    FailureCase,
    RequestContract,
    VerificationProfile,
)
from .execution import ExecutionPlan, ExecutionTier, VerificationMode
from .run_config import AntiBotType, CrawlRate, OutputFormat, RunConfig, RunMode
from .session_state import SessionState
from .signature import SignatureSpec
from .site_profile import BrowserAction, BrowserActionType, SiteProfile
from .target import (
    BatterySimulation,
    BrowserProfile,
    EnvironmentSimulation,
    InteractionSimulation,
    MediaSimulation,
    NetworkInformationSimulation,
    PointerPathSimulation,
    RequestCapture,
    TargetSite,
    WebGLSimulation,
)
from .trace import TraceArtifact, WorkflowCheckpoint
# Memory exports (consolidated)
try:
    from axelo.memory.db import MemoryDB
    from axelo.memory.vector_store import VectorStore
    from axelo.memory.retriever import MemoryRetriever
    from axelo.memory.writer import MemoryWriter
except Exception:  # pragma: no cover - compatibility path for partial imports
    MemoryDB = None
    VectorStore = None
    MemoryRetriever = None
    MemoryWriter = None

__all__ = [
    # Original models
    "AIHypothesis",
    "AnalysisResult",
    "AntiBotType",
    "BatterySimulation",
    "BrowserAction",
    "BrowserActionType",
    "BrowserProfile",
    "BridgeTargetCandidate",
    "CapabilityProfile",
    "CompliancePolicy",
    "CaptureIntent",
    "ExecutionPlan",
    "ExecutionTier",
    "CrawlRate",
    "DatasetContract",
    "DeobfuscationResult",
    "DynamicAnalysis",
    "EvidenceBundle",
    "EnvironmentSimulation",
    "FailureCase",
    "FunctionSignature",
    "GeneratedCode",
    "HookIntercept",
    "InteractionSimulation",
    "JSBundle",
    "MediaSimulation",
    "NetworkInformationSimulation",
    "OutputFormat",
    "PointerPathSimulation",
    "RequestContract",
    "RequestCapture",
    "RunConfig",
    "RunMode",
    "SessionState",
    "SignatureSpec",
    "SiteProfile",
    "StaticAnalysis",
    "TargetSite",
    "TaintEvent",
    "TaintSink",
    "TaintTopology",
    "TokenCandidate",
    "TraceArtifact",
    "VerificationProfile",
    "VerificationMode",
    "WebGLSimulation",
    "WorkflowCheckpoint",
    "AdapterPackage",
    # Memory exports
    "MemoryDB",
    "VectorStore",
    "MemoryRetriever",
    "MemoryWriter",
]
