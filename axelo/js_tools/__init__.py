"""
JS Tools Module (DEPRECATED)

This module has been moved to axelo.utils.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.js_tools is deprecated. "
    "Use axelo.utils instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .runner import NodeRunner, NodeRunnerError
from .deobfuscators import DeobfuscationPipeline

__all__ = ["NodeRunner", "NodeRunnerError", "DeobfuscationPipeline"]
