from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from axelo.core.artifacts.manager import ArtifactSessionManager
from axelo.core.artifacts.writer import ArtifactWriter
from axelo.core.logging.session_logger import session_context
from axelo.core.router.monitor import Monitor, MonitorDecision
from axelo.core.router.planner import Planner
from axelo.core.router.registry import AgentRegistry
from axelo.core.router.state_machine import SessionStatus, StateMachine

log = structlog.get_logger()


class Router:
    def __init__(
        self,
        registry: AgentRegistry,
        artifacts_root: Path | None = None,
    ) -> None:
        self.registry = registry
        self.planner = Planner()
        self.monitor = Monitor()
        self._artifacts_mgr = ArtifactSessionManager(artifacts_root)

    async def run(self, target_url: str, objective: str) -> dict[str, Any]:
        session_id = self._artifacts_mgr.create_session()
        session_path = self._artifacts_mgr.session_path(session_id)
        writer = ArtifactWriter(session_path)
        sm = StateMachine()

        with session_context(session_id=session_id, target_url=target_url):
            log.info("router_start", objective=objective)
            self._record_transition(writer, sm, SessionStatus.SESSION_PLANNING, "router_start")

            graph = await self.planner.plan(target_url, objective)
            self._record_transition(writer, sm, SessionStatus.SESSION_RUNNING, "plan_complete")
            writer.write_json("logs/task_graph.json", [t.model_dump() for t in graph.tasks])

            max_iterations = 20
            iterations = 0
            while not graph.is_complete() and iterations < max_iterations:
                iterations += 1
                ready = graph.ready_tasks()
                if not ready:
                    if graph.has_failure():
                        break
                    await asyncio.sleep(0.05)
                    continue

                results = await asyncio.gather(
                    *[self._run_task(task, writer) for task in ready],
                    return_exceptions=True,
                )

                for task, result in zip(ready, results):
                    if isinstance(result, Exception):
                        task.mark_failed(str(result))
                        continue
                    decision = self.monitor.evaluate(task.agent, result, graph, sm)
                    log.info("monitor_decision", agent=task.agent, decision=decision)
                    writer.append_jsonl("logs/monitor_decisions.jsonl", {
                        "at": datetime.now().isoformat(),
                        "agent": task.agent,
                        "decision": decision,
                    })
                    if decision == MonitorDecision.FAIL_SESSION:
                        self._record_transition(writer, sm, SessionStatus.SESSION_FAILED, decision)
                        return {"status": "failed", "session_id": session_id, "error": result.error}

            final_status = "complete" if graph.is_complete() and not graph.has_failure() else "failed"
            target_sm_status = (
                SessionStatus.SESSION_COMPLETE if final_status == "complete" else SessionStatus.SESSION_FAILED
            )
            self._record_transition(writer, sm, target_sm_status, "graph_finished")
            writer.write_json("final/session_report.json", {
                "session_id": session_id,
                "target_url": target_url,
                "objective": objective,
                "status": final_status,
                "completed_at": datetime.now().isoformat(),
                "state_history": sm.history,
                "agent_results": {
                    t.agent: t.result.model_dump(mode="json") if t.result else None
                    for t in graph.tasks
                },
            })
            log.info("router_done", status=final_status)
            return {"status": final_status, "session_id": session_id}

    async def _run_task(self, task, writer: ArtifactWriter):
        agent = self.registry.get(task.agent)
        result = await agent.run(task)
        writer.append_jsonl(f"logs/{task.agent}_events.jsonl", {
            "at": datetime.now().isoformat(),
            "agent": task.agent,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "error": result.error,
        })
        return result

    def _record_transition(
        self,
        writer: ArtifactWriter,
        sm: StateMachine,
        new_status: SessionStatus,
        reason: str = "",
    ) -> None:
        if sm.can_transition(new_status):
            sm.transition(new_status, reason=reason)
            writer.append_jsonl("logs/state_transitions.jsonl", {
                "from": sm.history[-1]["from"] if sm.history else None,
                "to": new_status.value,
                "at": sm.history[-1]["at"] if sm.history else None,
                "reason": reason,
            })
