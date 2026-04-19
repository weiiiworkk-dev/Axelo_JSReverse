# axelo/core/router/monitor.py
from __future__ import annotations

from enum import Enum

import structlog

from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask, TaskGraph, TaskStatus
from axelo.core.router.state_machine import SessionStatus, StateMachine

log = structlog.get_logger()


class MonitorDecision(str, Enum):
    CONTINUE = "continue"
    REQUEUE_CODEGEN = "requeue_codegen"
    REQUEUE_ANALYSIS = "requeue_analysis"
    RETRY_AGENT = "retry_agent"
    FAIL_SESSION = "fail_session"


_MAX_CODEGEN_RETRIES = 3
_MIN_REPLAY_SUCCESS_RATE = 0.8


class Monitor:
    def evaluate(
        self,
        agent: str,
        result: AgentResult,
        graph: TaskGraph,
        sm: StateMachine,
    ) -> MonitorDecision:
        log.info("monitor_evaluating", agent=agent, status=result.status, error=result.error)

        if result.ok:
            return MonitorDecision.CONTINUE

        if agent == "verification" and result.status == ResultStatus.FAILURE:
            codegen_task = graph.get_by_agent("codegen")
            if codegen_task and codegen_task.attempt < _MAX_CODEGEN_RETRIES:
                log.warning("monitor_requeue_codegen", attempt=codegen_task.attempt)
                codegen_task.status = TaskStatus.PENDING
                if verify_task := graph.get_by_agent("verification"):
                    verify_task.status = TaskStatus.PENDING
                return MonitorDecision.REQUEUE_CODEGEN
            return MonitorDecision.FAIL_SESSION

        if agent == "replay" and result.status == ResultStatus.FAILURE:
            success_rate = result.data.get("success_rate", 0.0)
            if success_rate < _MIN_REPLAY_SUCCESS_RATE:
                analysis_task = graph.get_by_agent("analysis")
                if analysis_task:
                    analysis_task.status = TaskStatus.PENDING
                    for downstream in ["codegen", "verification", "replay"]:
                        if t := graph.get_by_agent(downstream):
                            t.status = TaskStatus.PENDING
                log.warning("monitor_requeue_analysis", success_rate=success_rate)
                return MonitorDecision.REQUEUE_ANALYSIS

        task = graph.get_by_agent(agent)
        if task and task.attempt < 2:
            task.status = TaskStatus.PENDING
            log.warning("monitor_retry_agent", agent=agent, attempt=task.attempt)
            return MonitorDecision.RETRY_AGENT

        return MonitorDecision.FAIL_SESSION
