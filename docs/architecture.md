# Project Architecture

## Overview

Axelo uses a single AI conversation runtime.
Users start from terminal (`Axelo` / `axelo`), describe reverse-engineering and crawling requirements, confirm an AI-generated plan, and the system executes tools dynamically.

## Canonical Flow

1. Entry: `axelo/cli.py`
2. Chat loop: `axelo/chat/cli.py`
3. Router/planning: `axelo/chat/router.py`
4. Tool execution: `axelo/chat/executor.py`
5. Tool implementations: `axelo/tools/*.py`

## Planning and Execution

- The router collects required context (target + goal).
- AI returns a structured task plan and tool sequence.
- On confirmation, execution prefers the AI-planned tools.
- Execution results are returned in the same conversation session.

## Commands

- `Axelo` or `axelo`: interactive AI conversation.
- `axelo run <url> --goal "<goal>"`: non-interactive run through chat flow.
- `axelo chat`: explicit chat command.
- `axelo tools`: inspect tool registry.

## Source of Truth

This document and `README.md` define the active architecture.
Legacy orchestrator/UI paths are not part of the supported runtime contract.
