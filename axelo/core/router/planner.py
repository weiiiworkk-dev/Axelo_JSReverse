from __future__ import annotations

import json
import re
from typing import Any

import structlog

from axelo.core.models.task import SubTask, TaskGraph

log = structlog.get_logger()

_PLAN_PROMPT = """\
You are a web reverse-engineering orchestrator. Given a target URL and objective, output a JSON array of tasks.
Each task: {{"agent": "<name>", "objective": "<description>", "depends_on": [<agent names>]}}

Available agents (use only these names):
- recon       : identify anti-bot system and site profile
- browser     : launch browser, capture JS bundles and network trace
- analysis    : static + dynamic JS analysis, deobfuscation
- codegen     : generate Python signature implementation
- verification: verify generated code correctness
- replay      : replay real HTTP requests, measure success rate
- memory      : store successful patterns to vector database

Rules:
1. Always start with "recon"
2. "browser" depends on "recon"
3. "analysis" depends on "browser"
4. "codegen" depends on "analysis"
5. "verification" depends on "codegen"
6. "replay" depends on "verification"
7. "memory" depends on "replay"
8. Output ONLY valid JSON array, no prose.

Target URL: {url}
Objective: {objective}
"""


class Planner:
    async def plan(self, target_url: str, objective: str) -> TaskGraph:
        log.info("planner_start", url=target_url, objective=objective)
        raw = await self._call_llm(target_url, objective)
        tasks = self._parse(raw)
        graph = TaskGraph(tasks=tasks)
        log.info("planner_done", task_count=len(tasks), agents=[t.agent for t in tasks])
        return graph

    async def _call_llm(self, url: str, objective: str) -> str:
        from axelo.ai.unified import UnifiedAIClient
        client = UnifiedAIClient()
        prompt = _PLAN_PROMPT.format(url=url, objective=objective)
        return await client.complete(prompt)

    def _parse(self, raw: str) -> list[SubTask]:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            raise ValueError(f"Planner LLM did not return a JSON array. Got: {raw[:200]}")
        items: list[dict[str, Any]] = json.loads(match.group())
        return [
            SubTask(
                agent=item["agent"],
                objective=item.get("objective", ""),
                depends_on=item.get("depends_on", []),
            )
            for item in items
        ]
