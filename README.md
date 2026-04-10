# Axelo JSReverse

Axelo JSReverse is an AI-first reverse engineering and crawling assistant.

## Canonical Runtime

The only supported runtime path is:

1. Start from terminal with `Axelo` (or `axelo`).
2. CLI enters the AI conversation loop in `axelo/chat/cli.py`.
3. Router in `axelo/chat/router.py` gathers user intent (target + goal), asks for confirmation, and builds an execution plan.
4. The confirmed plan is executed through `axelo/chat/executor.py` and registered tools in `axelo/tools/`.

There is no legacy UI/runtime path in the active architecture.

## Commands

- `Axelo` / `axelo`: launch interactive AI conversation.
- `axelo run <url> --goal "<goal>"`: run non-interactive chat flow.
- `axelo chat`: explicit interactive chat entry.
- `axelo tools`: list registered tools.

## Tooling Flow

Typical AI-driven workflow:

1. Analyze target and requirements
2. Generate plan with tool sequence
3. Execute tools (e.g. `browser`, `fetch`, `static`, `crypto`, `ai_analyze`, `codegen`, `verify`)
4. Return results and generated crawler artifacts

## Requirements

- Python 3.11+
- Node.js
- Playwright
- LLM API key configured in environment

## Quick Validation

```bash
python -m axelo.cli
pytest
```
