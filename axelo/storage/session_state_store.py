from __future__ import annotations

import json
from pathlib import Path

from axelo.models.session_state import SessionState


class SessionStateStore:
    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def state_path(self, session_id: str) -> Path:
        return self._dir / session_id / "session_state.json"

    def browser_storage_path(self, session_id: str) -> Path:
        return self._dir / session_id / "browser_storage_state.json"

    def save(self, session_id: str, session_state: SessionState) -> Path:
        path = self.state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session_state.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> SessionState | None:
        path = self.state_path(session_id)
        if not path.exists():
            return None
        try:
            return SessionState.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_browser_storage(self, session_id: str, payload: dict) -> Path:
        path = self.browser_storage_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
