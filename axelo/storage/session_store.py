from __future__ import annotations
import json
from pathlib import Path
from axelo.models.pipeline import PipelineState
import structlog

log = structlog.get_logger()


class SessionStore:
    """
    基于 JSON 文件的轻量会话持久化。
    每个 session 存一个 state.json 文件，支持断点续跑。
    """

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, session_id: str) -> Path:
        return self._dir / session_id / "state.json"

    def save(self, state: PipelineState) -> None:
        path = self._state_path(state.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        log.debug("session_saved", session_id=state.session_id)

    def load(self, session_id: str) -> PipelineState | None:
        path = self._state_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PipelineState.model_validate(data)
        except Exception as e:
            log.warning("session_load_failed", session_id=session_id, error=str(e))
            return None

    def list_sessions(self) -> list[str]:
        return [p.parent.name for p in self._dir.glob("*/state.json")]

    def delete(self, session_id: str) -> None:
        path = self._state_path(session_id)
        if path.exists():
            path.unlink()
