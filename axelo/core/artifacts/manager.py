from __future__ import annotations

import re
from pathlib import Path

_SUBDIRS = ["logs", "recon", "browser", "analysis", "codegen", "verification", "replay", "final"]


class ArtifactSessionManager:
    def __init__(self, artifacts_root: Path | None = None) -> None:
        if artifacts_root is None:
            from axelo.config import settings
            artifacts_root = settings.workspace.parent / "artifacts"
        self.root = Path(artifacts_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _next_number(self) -> int:
        pattern = re.compile(r"^session_(\d{6})$")
        existing = [
            int(m.group(1))
            for d in self.root.iterdir()
            if d.is_dir() and (m := pattern.match(d.name))
        ]
        return max(existing, default=0) + 1

    def create_session(self) -> str:
        n = self._next_number()
        session_id = f"session_{n:06d}"
        session_path = self.root / session_id
        session_path.mkdir(parents=True, exist_ok=True)
        for sub in _SUBDIRS:
            (session_path / sub).mkdir(exist_ok=True)
        return session_id

    def session_path(self, session_id: str) -> Path:
        return self.root / session_id
