# Project Architecture

## Purpose

Axelo JSReverse is an AI-assisted reverse-engineering pipeline for web request signing, token generation, and obfuscated JavaScript analysis.

## Runtime Flow

1. User supplies a target URL and reverse-engineering goal.
2. The wizard or CLI builds a `RunConfig`.
3. `MasterOrchestrator` creates a `TargetSite` and resolves runtime policy.
4. `CrawlStage` captures requests, responses, and JS resources.
5. `FetchStage` downloads JS bundles.
6. `DeobfuscateStage` normalizes bundle content.
7. `StaticAnalysisStage` extracts candidate functions and call graphs.
8. `DynamicAnalysisStage` confirms runtime behavior with hooks.
9. `AIAnalysisStage` synthesizes the algorithm hypothesis.
10. `CodeGenStage` generates Python crawler code or a JS bridge.
11. `VerifyStage` replays the generated code and compares results.
12. `MemoryWriter` stores reusable patterns and templates.

## New Input Contract

The runtime now carries these user-provided context fields end-to-end:

- `known_endpoint`
- `antibot_type`
- `requires_login`
- `output_format`
- `crawl_rate`

These fields are consumed by:

- CLI and wizard input collection
- `RunConfig`
- `TargetSite`
- runtime policy resolution
- AI prompt templates
- output saving
- run reporting

## Key Modules

- `axelo/models/run_config.py`: canonical input schema.
- `axelo/policies/runtime.py`: maps target metadata to crawl behavior.
- `axelo/output/sink.py`: saves JSON/CSV outputs.
- `axelo/telemetry/report.py`: writes `run_report.json`.
- `axelo/verification/replayer.py`: loads generated code and replays requests.

## Important Note

There are two orchestration paths in the repository:

- `axelo/orchestrator/master.py` is the current main path.
- `axelo/session.py` remains as a compatibility-oriented pipeline wrapper.

New work should target `MasterOrchestrator` unless you explicitly need the legacy flow.

