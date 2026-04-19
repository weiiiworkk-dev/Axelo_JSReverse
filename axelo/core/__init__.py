"""
axelo.core — new architecture public API

Router AI + Sub-Agents architecture.
"""

from __future__ import annotations

from axelo.core.base_agent import BaseAgent
from axelo.core.models import AgentResult, ResultStatus, SessionState, SessionStatus, SubTask, TaskGraph, TaskStatus
from axelo.core.artifacts.manager import ArtifactSessionManager
from axelo.core.artifacts.writer import ArtifactWriter
from axelo.core.logging.logger import configure_logging, get_logger
from axelo.core.logging.session_logger import session_context

__all__ = [
    "BaseAgent",
    "AgentResult", "ResultStatus",
    "SessionState", "SessionStatus",
    "SubTask", "TaskGraph", "TaskStatus",
    "ArtifactSessionManager", "ArtifactWriter",
    "configure_logging", "get_logger", "session_context",
]
