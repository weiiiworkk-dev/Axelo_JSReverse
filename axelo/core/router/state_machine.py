# axelo/core/router/state_machine.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    # Session lifecycle
    SESSION_INIT        = "session_init"
    SESSION_PLANNING    = "session_planning"
    SESSION_RUNNING     = "session_running"
    SESSION_COMPLETE    = "session_complete"
    SESSION_FAILED      = "session_failed"
    # Recon
    RECON_QUEUED        = "recon_queued"
    RECON_RUNNING       = "recon_running"
    RECON_COMPLETE      = "recon_complete"
    RECON_FAILED        = "recon_failed"
    RECON_RETRYING      = "recon_retrying"
    # Browser
    BROWSER_QUEUED      = "browser_queued"
    BROWSER_RUNNING     = "browser_running"
    BROWSER_CAPTURING   = "browser_capturing"
    BROWSER_COMPLETE    = "browser_complete"
    BROWSER_FAILED      = "browser_failed"
    # Analysis
    ANALYSIS_QUEUED         = "analysis_queued"
    ANALYSIS_STATIC         = "analysis_static"
    ANALYSIS_DYNAMIC        = "analysis_dynamic"
    ANALYSIS_DEOBFUSCATING  = "analysis_deobfuscating"
    ANALYSIS_COMPLETE       = "analysis_complete"
    # Codegen
    CODEGEN_QUEUED      = "codegen_queued"
    CODEGEN_GENERATING  = "codegen_generating"
    CODEGEN_ITERATING   = "codegen_iterating"
    CODEGEN_COMPLETE    = "codegen_complete"
    CODEGEN_FAILED      = "codegen_failed"
    # Verification
    VERIFICATION_QUEUED     = "verification_queued"
    VERIFICATION_RUNNING    = "verification_running"
    VERIFICATION_COMPLETE   = "verification_complete"
    # Replay
    REPLAY_QUEUED       = "replay_queued"
    REPLAY_RUNNING      = "replay_running"
    REPLAY_EVALUATING   = "replay_evaluating"
    REPLAY_COMPLETE     = "replay_complete"
    # Memory
    MEMORY_QUEUED       = "memory_queued"
    MEMORY_WRITING      = "memory_writing"
    MEMORY_WRITTEN      = "memory_written"


# Valid forward transitions (SESSION_FAILED always allowed, not listed here)
_ALLOWED: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.SESSION_INIT:         {SessionStatus.SESSION_PLANNING},
    SessionStatus.SESSION_PLANNING:     {SessionStatus.SESSION_RUNNING, SessionStatus.RECON_QUEUED},
    SessionStatus.SESSION_RUNNING:      {SessionStatus.RECON_QUEUED, SessionStatus.BROWSER_QUEUED,
                                         SessionStatus.ANALYSIS_QUEUED, SessionStatus.CODEGEN_QUEUED,
                                         SessionStatus.SESSION_COMPLETE},
    SessionStatus.RECON_QUEUED:         {SessionStatus.RECON_RUNNING},
    SessionStatus.RECON_RUNNING:        {SessionStatus.RECON_COMPLETE, SessionStatus.RECON_FAILED},
    SessionStatus.RECON_FAILED:         {SessionStatus.RECON_RETRYING},
    SessionStatus.RECON_RETRYING:       {SessionStatus.RECON_RUNNING},
    SessionStatus.RECON_COMPLETE:       {SessionStatus.BROWSER_QUEUED, SessionStatus.SESSION_RUNNING},
    SessionStatus.BROWSER_QUEUED:       {SessionStatus.BROWSER_RUNNING},
    SessionStatus.BROWSER_RUNNING:      {SessionStatus.BROWSER_CAPTURING, SessionStatus.BROWSER_FAILED},
    SessionStatus.BROWSER_CAPTURING:    {SessionStatus.BROWSER_COMPLETE, SessionStatus.BROWSER_FAILED},
    SessionStatus.BROWSER_COMPLETE:     {SessionStatus.ANALYSIS_QUEUED, SessionStatus.SESSION_RUNNING},
    SessionStatus.ANALYSIS_QUEUED:      {SessionStatus.ANALYSIS_STATIC},
    SessionStatus.ANALYSIS_STATIC:      {SessionStatus.ANALYSIS_DYNAMIC, SessionStatus.ANALYSIS_COMPLETE},
    SessionStatus.ANALYSIS_DYNAMIC:     {SessionStatus.ANALYSIS_DEOBFUSCATING, SessionStatus.ANALYSIS_COMPLETE},
    SessionStatus.ANALYSIS_DEOBFUSCATING: {SessionStatus.ANALYSIS_COMPLETE},
    SessionStatus.ANALYSIS_COMPLETE:    {SessionStatus.CODEGEN_QUEUED, SessionStatus.SESSION_RUNNING},
    SessionStatus.CODEGEN_QUEUED:       {SessionStatus.CODEGEN_GENERATING},
    SessionStatus.CODEGEN_GENERATING:   {SessionStatus.CODEGEN_ITERATING, SessionStatus.CODEGEN_COMPLETE, SessionStatus.CODEGEN_FAILED},
    SessionStatus.CODEGEN_ITERATING:    {SessionStatus.CODEGEN_GENERATING, SessionStatus.CODEGEN_COMPLETE, SessionStatus.CODEGEN_FAILED},
    SessionStatus.CODEGEN_COMPLETE:     {SessionStatus.VERIFICATION_QUEUED},
    SessionStatus.VERIFICATION_QUEUED:  {SessionStatus.VERIFICATION_RUNNING},
    SessionStatus.VERIFICATION_RUNNING: {SessionStatus.VERIFICATION_COMPLETE, SessionStatus.CODEGEN_QUEUED},
    SessionStatus.VERIFICATION_COMPLETE:{SessionStatus.REPLAY_QUEUED},
    SessionStatus.REPLAY_QUEUED:        {SessionStatus.REPLAY_RUNNING},
    SessionStatus.REPLAY_RUNNING:       {SessionStatus.REPLAY_EVALUATING},
    SessionStatus.REPLAY_EVALUATING:    {SessionStatus.REPLAY_COMPLETE, SessionStatus.ANALYSIS_QUEUED},
    SessionStatus.REPLAY_COMPLETE:      {SessionStatus.MEMORY_QUEUED},
    SessionStatus.MEMORY_QUEUED:        {SessionStatus.MEMORY_WRITING},
    SessionStatus.MEMORY_WRITING:       {SessionStatus.MEMORY_WRITTEN},
    SessionStatus.MEMORY_WRITTEN:       {SessionStatus.SESSION_COMPLETE},
}


class InvalidTransitionError(Exception):
    pass


class StateMachine:
    def __init__(self) -> None:
        self.status: SessionStatus = SessionStatus.SESSION_INIT
        self.history: list[dict[str, Any]] = []

    def transition(self, new_status: SessionStatus, reason: str = "") -> None:
        allowed = _ALLOWED.get(self.status, set()) | {SessionStatus.SESSION_FAILED}
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {self.status.value!r} to {new_status.value!r}"
            )
        self.history.append({
            "from": self.status.value,
            "to": new_status.value,
            "at": datetime.now().isoformat(),
            "reason": reason,
        })
        self.status = new_status

    def can_transition(self, new_status: SessionStatus) -> bool:
        allowed = _ALLOWED.get(self.status, set()) | {SessionStatus.SESSION_FAILED}
        return new_status in allowed
