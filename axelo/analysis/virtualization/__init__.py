"""
axelo.analysis.virtualization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Architecture for detecting and analysing VM-based / virtualization-obfuscated
JavaScript.

Exported symbols
----------------
VirtualizationDetector  — identify VM patterns in JS source
VMDetectionResult       — result model from the detector
BytecodeExtractor       — pull bytecode, constant pool, and handler map
BytecodeExtract         — result model from the extractor
VMReplicator            — build a JS-bridge or Python-interpreter replica
VMReplicaStrategy       — strategy enum for the replicator
run_vm_analysis         — convenience function wiring all three together
"""

from axelo.analysis.virtualization.detector import (
    VirtualizationDetector,
    VMDetectionResult,
)
from axelo.analysis.virtualization.extractor import (
    BytecodeExtract,
    BytecodeExtractor,
)
from axelo.analysis.virtualization.replicator import (
    VMReplicaStrategy,
    VMReplicator,
)
from axelo.analysis.virtualization.integration import run_vm_analysis

__all__ = [
    "VirtualizationDetector",
    "VMDetectionResult",
    "BytecodeExtract",
    "BytecodeExtractor",
    "VMReplicaStrategy",
    "VMReplicator",
    "run_vm_analysis",
]
