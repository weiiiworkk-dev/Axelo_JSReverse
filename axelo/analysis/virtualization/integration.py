"""
Pipeline integration for VM analysis.

This module exposes ``run_vm_analysis()``, which is called from:
  - S3 (DeobfuscateStage) — to detect VM patterns after deobfuscation
  - S4 (StaticAnalysisStage) — to extract bytecode and write replicas

The two-phase design keeps the detection cheap (regex, no Node.js) and
only escalates to the heavier extraction + replication path when the
detector returns high confidence (>= 0.6).
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from axelo.analysis.virtualization.detector import VMDetectionResult, VirtualizationDetector
from axelo.analysis.virtualization.extractor import BytecodeExtractor
from axelo.analysis.virtualization.replicator import VMReplicaStrategy, VMReplicator

log = structlog.get_logger(__name__)

_detector   = VirtualizationDetector()
_extractor  = BytecodeExtractor()
_replicator = VMReplicator()

# Minimum confidence required to proceed to extraction
_EXTRACTION_THRESHOLD = 0.60


def run_vm_analysis(
    bundle_id: str,
    source: str,
    output_dir: Path,
    ast_data: dict | None = None,
    node_runner=None,          # axelo.js_tools.runner.NodeRunner | None
    strategy: VMReplicaStrategy = VMReplicaStrategy.JS_BRIDGE,
    ai_client=None,
    precomputed_detection: VMDetectionResult | None = None,  # 传入 S3 已有结果，跳过重复检测
) -> VMDetectionResult:
    """
    Run the full VM analysis pipeline on a single JS bundle.

    Steps
    -----
    1. **Detect** — regex scan for dispatch loop / opcode table / bytecode array
    2. **Extract** — if confidence ≥ 0.6, extract bytecode + constant pool
    3. **Replicate** — build a JS-bridge (default) or Python interpreter
    4. **Write** — save replica to ``output_dir/{bundle_id}_vm_replica.js``

    Parameters
    ----------
    bundle_id:
        Unique identifier for the JS bundle (used in log messages and filenames).
    source:
        Raw or deobfuscated JS source text.
    output_dir:
        Directory where the replica and detection report will be written.
        Created automatically if it does not exist.
    ast_data:
        Optional pre-parsed AST data from ASTAnalyzer (can improve precision).
    node_runner:
        Optional NodeRunner instance.  If provided and regex extraction fails,
        the extractor will fall back to a Node.js-based AST traversal.
    strategy:
        Which replication strategy to use (JS_BRIDGE by default).
    ai_client:
        Only required when strategy=AI_DECOMPILE.

    Returns
    -------
    VMDetectionResult
        Always returned (detected=False when no VM found).
    """
    # Phase 1 — Detection（若传入 S3 已有结果则跳过重复检测）
    detection = precomputed_detection if precomputed_detection is not None else _detector.detect(source, ast_data)

    if not detection.detected:
        log.debug(
            "vm_not_detected",
            bundle_id=bundle_id,
            confidence=detection.confidence,
        )
        return detection

    log.info(
        "vm_detected",
        bundle_id=bundle_id,
        confidence=detection.confidence,
        patterns=detection.pattern_types,
        dense_switches=detection.dense_switch_count,
    )

    if detection.confidence < _EXTRACTION_THRESHOLD:
        log.debug(
            "vm_extraction_skipped_low_confidence",
            bundle_id=bundle_id,
            confidence=detection.confidence,
            threshold=_EXTRACTION_THRESHOLD,
        )
        return detection

    # Phase 2 — Extraction
    extract = _extractor.extract(source, detection, node_runner)
    if extract is None:
        log.warning("vm_extraction_failed", bundle_id=bundle_id)
        return detection

    log.info(
        "vm_extracted",
        bundle_id=bundle_id,
        bytecode_len=len(extract.raw_bytecode),
        pool_size=len(extract.constant_pool),
        handlers=len(extract.handler_map),
        vm_func=extract.vm_function_name,
    )

    # Phase 3 — Replication
    try:
        replica_source = _replicator.build(extract, strategy=strategy, ai_client=ai_client)
    except Exception as exc:
        log.warning("vm_replication_failed", bundle_id=bundle_id, error=str(exc))
        return detection

    # Phase 4 — Write artefacts
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = ".js" if strategy == VMReplicaStrategy.JS_BRIDGE else ".py"
    replica_path = output_dir / f"{bundle_id}_vm_replica{ext}"
    replica_path.write_text(replica_source, encoding="utf-8")

    # Also write a detection report JSON
    report_path = output_dir / f"{bundle_id}_vm_detection.json"
    report_path.write_text(
        json.dumps(
            {
                "detection":  detection.to_dict(),
                "extraction": {
                    "bytecode_len":    len(extract.raw_bytecode),
                    "bytecode_sample": extract.raw_bytecode[:32],
                    "pool_size":       len(extract.constant_pool),
                    "pool_sample":     extract.constant_pool[:10],
                    "handler_opcodes": sorted(int(k) for k in extract.handler_map.keys()),
                    "vm_func":         extract.vm_function_name,
                    "bytecode_var":    extract.bytecode_var_name,
                },
                "replica_strategy": strategy.value,
                "replica_path":     str(replica_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info(
        "vm_replica_written",
        bundle_id=bundle_id,
        replica=str(replica_path),
        report=str(report_path),
    )

    return detection
