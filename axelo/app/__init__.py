"""Application-layer flows and typed artifacts for the Axelo runtime."""

# Flows
from .artifacts import DiscoveryArtifacts, AnalysisArtifacts

# Modes (consolidated)
from axelo.modes import (
    ModeController,
    InteractiveMode,
    AutoMode,
    ManualMode,
    create_mode,
    available_modes,
)

__all__ = [
    "DiscoveryArtifacts",
    "AnalysisArtifacts",
    "ModeController",
    "InteractiveMode",
    "AutoMode",
    "ManualMode",
    "create_mode",
    "available_modes",
]
