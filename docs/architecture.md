# Project Architecture

## Overview

The runtime is mission-driven.

The system no longer builds a fixed tool plan and then executes it. A principal state is created from the request, the constitution evaluates evidence coverage and blockers, and the runtime dispatches the next objective accordingly.

## Active Flow

1. `axelo/cli.py`
2. `axelo/chat/cli.py`
3. `axelo/engine/runtime.py`
4. `axelo/engine/principal.py`
5. `axelo/engine/constitution.py`
6. `axelo/engine/subagents.py`
7. `axelo/engine/artifacts.py`

## Runtime Contract

- Mission framing is stored as a mission brief, not as a precomputed task queue.
- Next actions are produced from state, not from tool-name follow-up rules.
- Sub-agents are capability agents.
- Tools are execution affordances inside an objective, not the top-level workflow definition.
- Finalization is gated by trust, blockers, and verification evidence.

## Supported Outputs

Only the following outputs are part of the supported contract:

- `workspace/sessions/AAA/AAA-000001/` style nested site-session directories
- `session_request.json`
- `logs/principal_state.json`
- `artifacts/agent_runs/*.json`
- `artifacts/final/mission_brief.json`
- `artifacts/final/mission_report.json`
- `artifacts/final/evidence_graph.json`
- `artifacts/final/artifact_index.json`
- `artifacts/generated/*`

Old queue, review, and stage summary files are intentionally removed from the runtime contract.
