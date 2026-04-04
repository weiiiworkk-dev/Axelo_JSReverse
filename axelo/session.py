from __future__ import annotations

from axelo.models.pipeline import PipelineState
from axelo.orchestrator import MasterOrchestrator
from axelo.storage import SessionStore
from axelo.config import settings


class EngineSession:
    """Thin facade over the canonical MasterOrchestrator runtime."""

    def __init__(self) -> None:
        self._store = SessionStore(settings.sessions_dir)
        self._master = MasterOrchestrator()

    async def run(
        self,
        url: str,
        goal: str,
        target_hint: str = "",
        mode_name: str = "interactive",
        session_id: str | None = None,
        resume: bool = False,
        known_endpoint: str = "",
        antibot_type: str = "unknown",
        requires_login: bool | None = None,
        output_format: str = "print",
        crawl_rate: str = "standard",
    ) -> PipelineState:
        result = await self._master.run(
            url=url,
            goal=goal,
            target_hint=target_hint,
            mode_name=mode_name,
            session_id=session_id,
            resume=resume,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
        )
        state = self._store.load(result.session_id)
        return state or PipelineState(
            session_id=result.session_id,
            mode=mode_name,
            completed=result.completed,
            error=result.error,
            workflow_status="completed" if result.completed else "failed",
        )

    def switch_mode(self, state: PipelineState, new_mode: str) -> None:
        state.mode = new_mode
        self._store.save(state)

    def list_sessions(self) -> list[str]:
        return self._store.list_sessions()
