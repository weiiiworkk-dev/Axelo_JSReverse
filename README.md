# Axelo JSReverse

Axelo JSReverse now runs on a single principal-agent runtime.

## Canonical Runtime

1. Entry starts from `axelo/cli.py`.
2. Interactive and non-interactive flows both enter `axelo/chat/cli.py`.
3. `axelo/engine/runtime.py` creates a mission brief and boots a principal state.
4. `axelo/engine/constitution.py` chooses the next objective from evidence gaps and blockers.
5. `axelo/engine/subagents.py` dispatches capability agents that may use one or more tools internally.
6. `axelo/engine/artifacts.py` persists only mission-driven outputs.

There is no precomputed task queue, central routing stage, or review-based follow-up chain in the active architecture.

## Outputs

Each run writes a session under `workspace/sessions/<site-code>/<session-id>` such as `workspace/sessions/AAA/AAA-000001` with:

- `session_request.json`
- `logs/principal_state.json`
- `artifacts/agent_runs/*.json`
- `artifacts/final/mission_brief.json`
- `artifacts/final/mission_report.json`
- `artifacts/final/evidence_graph.json`
- `artifacts/final/artifact_index.json`
- `artifacts/generated/*` when code or hooks are produced

Removed outputs such as `plan.json`, queue-review logs, `review_*.json`, `reverse_summary.json`, and `crawl_summary.json` are no longer part of the runtime contract.

## Commands

- `Axelo` / `axelo`: launch the interactive mission intake flow.
- `axelo run <url> --goal "<goal>"`: run the non-interactive mission flow.
- `axelo chat`: explicit interactive entry.
- `axelo tools`: list registered tools.

## Quick Validation

```bash
python -m axelo.cli
pytest tests/unit/test_unified_engine.py tests/unit/test_subagent_manager.py tests/unit/test_engine_constitution.py
```
