# Project Architecture

## Overview

Axelo JSReverse is a staged reverse-engineering system for browser-driven request discovery, JavaScript analysis, signature reconstruction, crawler generation, and result verification.

The current implementation is organized around a single primary orchestration path:

- `axelo/orchestrator/master.py`

Legacy compatibility remains available through:

- `axelo/session.py`

All new features should target the master orchestrator path.

## Control Plane

Purpose:

- collect user intent
- normalize runtime inputs
- attach compliance and site metadata

Main components:

- `axelo/cli.py`
- `axelo/wizard.py`
- `axelo/models/run_config.py`
- `axelo/models/target.py`
- `axelo/models/site_profile.py`
- `axelo/models/compliance.py`

Important characteristics:

- one canonical `RunConfig`
- 9-step wizard
- user-provided crawl context carried end-to-end

## Workflow Plane

Purpose:

- coordinate stages
- persist checkpoints
- support resume and manual review

Main components:

- `axelo/orchestrator/master.py`
- `axelo/orchestrator/workflow_runtime.py`
- `axelo/orchestrator/recovery.py`
- `axelo/storage/workflow_store.py`

Important characteristics:

- stage-level checkpoint writes
- recoverable workflow metadata
- explicit `waiting_manual_review` state for extreme targets

## Execution Plane

Purpose:

- open browser sessions
- run page actions
- capture network activity
- persist browser state
- manage session health

Main components:

- `axelo/browser/driver.py`
- `axelo/browser/action_runner.py`
- `axelo/browser/interceptor.py`
- `axelo/browser/state_store.py`
- `axelo/browser/session_pool.py`
- `axelo/browser/trace_capture.py`
- `axelo/storage/session_state_store.py`

Important characteristics:

- Playwright storage-state persistence
- cookie persistence
- file-backed session pool
- trace artifact generation
- action-flow execution beyond simple `goto`

## Analysis Plane

Purpose:

- classify difficulty
- analyze bundles and runtime behavior
- derive structured signature metadata

Main components:

- `axelo/pipeline/stages/s4_static.py`
- `axelo/pipeline/stages/s5_dynamic.py`
- `axelo/pipeline/stages/s6_ai_analyze.py`
- `axelo/classifier/rules.py`
- `axelo/analysis/signature_spec_builder.py`
- `axelo/models/signature.py`
- `axelo/models/analysis.py`

Important characteristics:

- natural-language AI hypothesis output
- structured `SignatureSpec` output
- explicit manual-review routing for extreme difficulty

## Delivery Plane

Purpose:

- generate crawler artifacts
- emit runtime manifests
- replay and validate generated behavior

Main components:

- `axelo/pipeline/stages/s7_codegen.py`
- `axelo/agents/codegen_agent.py`
- `axelo/verification/replayer.py`
- `axelo/verification/engine.py`
- `axelo/verification/data_quality.py`
- `axelo/verification/stability.py`
- `axelo/output/sink.py`

Important characteristics:

- Python crawler or JS bridge generation
- crawler manifest generation
- data-quality scoring
- repeated-run stability validation

## Observability Plane

Purpose:

- record run metadata
- preserve trace and session artifacts
- support audit and debugging

Main components:

- `axelo/telemetry/report.py`
- `axelo/models/trace.py`

Important characteristics:

- structured `run_report.json`
- session-state artifact references
- trace file references
- workflow status serialization

## End-to-End Flow

1. Input is collected through CLI or wizard into `RunConfig`
2. `MasterOrchestrator` creates `TargetSite`, runtime policy, workflow state, and trace metadata
3. `CrawlStage` executes browser actions, records network captures, persists session state, and stores a Playwright trace
4. Fetch, deobfuscation, static analysis, and dynamic analysis stages build evidence
5. AI analysis and `SignatureSpec` construction produce machine-usable signature metadata
6. Code generation emits crawler artifacts and a manifest
7. Verification replays the crawler and evaluates correctness, data quality, and stability
8. Memory write-back stores reusable knowledge
9. The orchestrator finalizes the run report and latest workflow checkpoint

## Main Runtime Models

- `TargetSite`
  - target metadata, compliance, session state, trace info, and user context
- `PipelineState`
  - current stage, workflow status, review reason, and artifact paths
- `SessionState`
  - cookies, Playwright storage-state path, local values, and login metadata
- `SiteProfile`
  - domain-specific capability flags and notes
- `CompliancePolicy`
  - controls manual-review and stability requirements
- `SignatureSpec`
  - executable intermediate representation of the signing strategy
- `TraceArtifact`
  - trace file paths and capture metadata

## Current Guarantees

- full unit-test suite passes
- mock integration pipeline passes
- full test suite passes in the current repository state
- workflow state, session state, and trace metadata are persisted as files

## Design Intent

The system is designed for staged automation with auditability and human control, not for opaque single-shot generation. The most important design choices in the current architecture are:

- a single primary orchestration path
- structured runtime models instead of ad-hoc dictionaries
- explicit recovery artifacts
- explicit manual review for high-risk targets
- verification that measures more than basic header matching
