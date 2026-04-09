"""
Centralised helpers for naming run output artefacts.

All output files for a given run follow the pattern:
    workspace/sessions/{run_id}/{run_id}_<kind>.<ext>

This module is the single source of truth for those names so that the wizard,
orchestrator, codegen stage, sink, and presentation layer all stay in sync.
"""
from __future__ import annotations

from pathlib import Path


def run_output_paths(session_dir: Path, run_id: str) -> dict[str, Path]:
    """
    Return a mapping of logical artefact names to their absolute paths.

    Keys
    ----
    log       — structured run log
    crawler   — generated Python crawler script
    bridge    — optional JS bridge server
    json      — crawled data (JSON)
    csv       — crawled data (CSV)
    report    — full run report
    manifest  — codegen manifest
    """
    return {
        "log":      session_dir / f"{run_id}.log",
        "crawler":  session_dir / f"{run_id}_crawler.py",
        "bridge":   session_dir / f"{run_id}_bridge_server.js",
        "json":     session_dir / f"{run_id}_results.json",
        "csv":      session_dir / f"{run_id}_results.csv",
        "report":   session_dir / f"{run_id}_report.json",
        "manifest": session_dir / f"{run_id}_manifest.json",
    }
