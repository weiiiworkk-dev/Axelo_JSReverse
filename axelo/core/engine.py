"""
Unified Core Engine Module

New Tool-Based Architecture Version 2.0
Created: 2026-04-08

Note: The old orchestrator/pipeline modules have been removed.
Use axelo.tools and axelo.chat for the new architecture.
"""

import warnings

# Lazy loading for backward compatibility - may return None if modules don't exist
def __getattr__(name):
    # Orchestrator modules - removed
    if name in ["MasterOrchestrator", "OrchestratorRuntime", "WorkflowRuntime"]:
        warnings.warn(
            f"axelo.core.{name} is deprecated. Use axelo.chat.cli.AxeloChatCLI instead.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            if name == "MasterOrchestrator":
                from axelo.orchestrator.master import MasterOrchestrator
                return MasterOrchestrator
            elif name == "OrchestratorRuntime":
                from axelo.orchestrator.runtime import OrchestratorRuntime
                return OrchestratorRuntime
            elif name == "WorkflowRuntime":
                from axelo.orchestrator.workflow_runtime import WorkflowRuntime
                return WorkflowRuntime
        except ImportError:
            raise AttributeError(f"module {__name__!r} does not have {name!r} (orchestrator removed)")
    
    # Pipeline modules - removed
    if name in ["PipelineStage", "PipelineOrchestrator"]:
        warnings.warn(
            f"axelo.core.{name} is deprecated. Use axelo.tools instead.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            if name == "PipelineStage":
                from axelo.pipeline.base import PipelineStage
                return PipelineStage
            elif name == "PipelineOrchestrator":
                from axelo.pipeline.orchestrator import PipelineOrchestrator
                return PipelineOrchestrator
        except ImportError:
            raise AttributeError(f"module {__name__!r} does not have {name!r} (pipeline removed)")
    
    # Planner modules - check if available
    if name in ["Planner", "ExecutionPlan"]:
        try:
            from axelo.planner.strategy import Planner, ExecutionPlan
            return Planner if name == "Planner" else ExecutionPlan
        except ImportError:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    
    # Behavior modules - check if available
    if name in ["BehaviorMixer", "MouseSimulator", "ReplayBank"]:
        try:
            from axelo.behavior import BehaviorMixer, MouseSimulator, ReplayBank
            return locals().get(name)
        except ImportError:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    
    # Policy modules - check if available
    if name == "PolicyRuntime":
        try:
            from axelo.policies.runtime import PolicyRuntime
            return PolicyRuntime
        except ImportError:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "MasterOrchestrator",
    "OrchestratorRuntime",
    "WorkflowRuntime",
    "PipelineStage",
    "PipelineOrchestrator",
    "Planner",
    "ExecutionPlan",
    "BehaviorMixer",
    "MouseSimulator",
    "ReplayBank",
    "PolicyRuntime",
]