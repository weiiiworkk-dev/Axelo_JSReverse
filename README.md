# Axelo JSReverse

Axelo JSReverse is an AI-assisted reverse-engineering pipeline for web request signing, token generation, and obfuscated JavaScript analysis. It captures browser traffic and bundles, performs static and dynamic analysis, builds a structured signature model, generates runnable crawler code, and verifies the result before storing reusable knowledge.

The repository now also includes a platform layer for cluster-oriented operation:

- control-plane job submission
- URL frontier seeding and scheduling
- adapter version registry
- account/proxy lease management
- worker-based execution for reverse / crawl / bridge / session refresh
- local event bus, object store, and warehouse sinks that mirror the future Redis/Kafka/S3/ClickHouse split

## What Is Implemented

- Unified input contract through `RunConfig`
- Interactive 9-step wizard and CLI entrypoint
- Persistent `SessionState` with Playwright storage state and cookie support
- Browser `ActionRunner` for scripted crawl flows beyond static navigation
- File-backed `SessionPool` with health tracking and block detection
- `Planner`-driven execution tiers with adapter reuse before expensive analysis
- `AdapterRegistry` for verified crawler/artifact reuse across runs
- `CostGovernor` for budget-aware degradation and lighter verification modes
- Explicit manual review gate for `extreme` targets
- Structured `SignatureSpec` generation in addition to natural-language hypotheses
- Real Anthropic usage accounting wired into runtime cost records
- Verification replay executed in a dedicated subprocess instead of in-process imports
- Streaming JavaScript bundle downloads with early size guardrails
- Verification extended with header comparison, data-quality checks, and stability checks
- Workflow checkpoints, recovery metadata, and structured run reporting

## Runtime Architecture

Primary runtime path:

1. `axelo/wizard.py` or `axelo/cli.py` builds a `RunConfig`
2. `axelo/orchestrator/master.py` builds a `TargetSite`, asks the `Planner` for an `ExecutionPlan`, and starts workflow tracking
3. `axelo/storage/adapter_registry.py` is checked before any expensive browser or AI stage
4. `axelo/pipeline/stages/s1_crawl.py` opens the target in Playwright only when the plan requires it, executes actions, captures traffic, rotates sessions, and persists session state
5. `axelo/pipeline/stages/s2_fetch.py` downloads JavaScript bundles
6. `axelo/pipeline/stages/s3_deobfuscate.py` normalizes bundle content
7. `axelo/pipeline/stages/s4_static.py` extracts candidates using static analysis
8. `axelo/pipeline/stages/s5_dynamic.py` validates runtime behavior when the plan and budget still allow it
9. `axelo/pipeline/stages/s6_ai_analyze.py` produces AI hypotheses and a structured `SignatureSpec`
10. `axelo/pipeline/stages/s7_codegen.py` generates Python crawler code or a JS bridge plus a crawler manifest
11. `axelo/pipeline/stages/s8_verify.py` runs the canonical verification flow and persists the latest verification report
12. `axelo/memory` stores reusable patterns

Facade path:

- `axelo/session.py` remains available as a thin facade over the same runtime, not as a separate architecture

## Platform Architecture

The new platform layer lives under `axelo/platform/` and adds:

- `PlatformRuntime`
  - boots the platform metadata store, event bus, object store, and warehouse sink
- `ControlPlaneService`
  - accepts reverse, crawl, bridge, and session-refresh jobs
- `FrontierService`
  - deduplicates and persists frontier URLs before dispatch
- `SchedulerService`
  - turns ready frontier items into crawl jobs and requests reverse jobs when adapters are missing
- `ResourceManager`
  - manages account/proxy inventory and lease allocation
- `ReverseWorker`
  - wraps `MasterOrchestrator` and registers versioned adapters after verification
- `CrawlWorker`
  - executes verified `python_reconstruct` adapters directly
- `BridgeWorker`
  - handles `js_bridge` adapters as dedicated browser-bound jobs
- `SessionRefreshWorker`
  - refreshes browser session state and writes it back to account inventory

## Key Modules

- `axelo/models/`
  - canonical runtime models including `TargetSite`, `PipelineState`, `SessionState`, `SiteProfile`, `CompliancePolicy`, `TraceArtifact`, `ExecutionPlan`, and `SignatureSpec`
- `axelo/planner/`
  - execution planning and tier selection
- `axelo/browser/`
  - browser driver, action runner, state persistence helpers, session pool, trace capture
- `axelo/storage/adapter_registry.py`
  - verified crawler/artifact reuse registry
- `axelo/cost/governor.py`
  - budget-aware plan degradation and verification tuning
- `axelo/policies/runtime.py`
  - maps target metadata plus execution tier to crawl timing and browser policy
- `axelo/orchestrator/`
  - master orchestration, workflow checkpoints, recovery helpers
- `axelo/analysis/`
  - static and dynamic analysis plus structured signature-spec building
- `axelo/verification/`
  - replay engine, token comparison, data-quality checks, stability checks
- `axelo/output/sink.py`
  - output formatting and file persistence
- `axelo/telemetry/report.py`
  - structured `run_report.json` generation

## Input Contract

The runtime carries these fields end-to-end:

- `url`
- `goal`
- `known_endpoint`
- `antibot_type`
- `requires_login`
- `output_format`
- `crawl_rate`
- `mode`
- `budget`

The extra context is injected into:

- wizard and CLI prompts
- `TargetSite`
- runtime policy resolution
- AI prompts
- code generation manifest
- run reports

## Wizard Flow

1. URL
2. Goal
3. Target endpoint characteristic
4. Anti-bot type
5. Login requirement
6. Output format
7. Crawl rate
8. Runtime mode
9. AI budget

## Outputs

Each run may produce:

- `crawl/captures.json`
- `crawl/target.json`
- `crawl/browser_storage_state.json`
- `crawl/session_state.json`
- `crawl/playwright_trace.zip`
- `output/crawler.py`
- `output/bridge_server.js`
- `output/requirements.txt`
- `output/crawler_manifest.json`
- `run_report.json`
- adapter-registry entries under `workspace/adapter_registry/`
- workflow checkpoint files under the workflow store

Platform-mode outputs additionally include:

- `workspace/platform/metadata.db`
- `workspace/platform/events/*.jsonl`
- `workspace/platform/object_store/**`
- `workspace/platform/warehouse/**`
- versioned adapter artifacts under the local object-store mirror

## Execution Tiers

- `adapter_reuse`
  - reuses a previously verified crawler and manifest before opening a browser
- `browser_light`
  - reduced-cost browser discovery for known endpoints or constrained budgets
- `browser_full`
  - full action flow, analysis, codegen, and strict verification
- `manual_review`
  - stops early with a recoverable manual-review checkpoint

## Manual Review Gate

Targets classified as `extreme` no longer continue through unrestricted automatic retries. When compliance requires it, the orchestrator writes a workflow checkpoint, records the manual-review reason, and stops the pipeline in a recoverable state.

## Verification Model

Verification now checks:

- request/response compatibility
- token/header matching
- data quality of generated output
- repeated-run stability

## Validation Commands

```bash
cd axelo/js_tools/scripts && npm ci
python -c "from axelo.models.target import TargetSite; print('ok')"
python -c "from axelo.orchestrator.master import MasterOrchestrator; print('ok')"
pytest
```

Platform smoke examples:

```bash
axelo submit reverse https://example.com --goal "分析签名"
axelo frontier seed https://example.com/item/1 https://example.com/item/2
axelo serve scheduler --once
axelo worker run --type reverse-worker --once
axelo worker run --type crawl-worker --once
```

## Requirements

- Python 3.11+
- Node.js
- Playwright
- Anthropic API key

## Environment

Common configuration lives in `.env` and uses the `AXELO_` prefix:

- `AXELO_MODEL`
- `AXELO_WORKSPACE`
- `AXELO_NODE_BIN`
- `AXELO_BROWSER`
- `AXELO_HEADLESS`
- `AXELO_LOG_LEVEL`
- `AXELO_MAX_DYNAMIC_RETRIES`
- `AXELO_VERIFICATION_SUBPROCESS_TIMEOUT_SEC`
- `AXELO_BUNDLE_DOWNLOAD_BYTE_CAP_KB`
- `AXELO_PLATFORM_MODE`
- `AXELO_PLATFORM_DATABASE_URL`
- `AXELO_PLATFORM_ENVIRONMENT`
- `AXELO_PLATFORM_REGION`
- `AXELO_CONTROL_API_HOST`
- `AXELO_CONTROL_API_PORT`
- `AXELO_PLATFORM_POLL_INTERVAL_SEC`

## Notes

- New work should target `MasterOrchestrator`
- `axelo/session.py` should be treated as a thin facade over the canonical runtime
- Workflow checkpoints and session artifacts are intended to support pause, recovery, and human-in-the-loop review
- `axelo/js_tools/scripts/node_modules/` is intentionally not vendored; install it with `npm ci`
