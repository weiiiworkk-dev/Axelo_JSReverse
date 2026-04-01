from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
import json
from pathlib import Path
from urllib.parse import urlparse

from axelo.models.session_state import SessionState


def _slugify(domain: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", domain).strip("_") or "default"


class SessionPool:
    def __init__(self, base_dir: Path) -> None:
        self._dir = base_dir / "_pool"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _pool_path(self, domain: str) -> Path:
        return self._dir / f"{_slugify(domain)}.json"

    def _load_pool(self, domain: str) -> list[SessionState]:
        path = self._pool_path(domain)
        if not path.exists():
            return []
        try:
            payload = path.read_text(encoding="utf-8")
            return [SessionState.model_validate(item) for item in json.loads(payload)]
        except Exception:
            return []

    def _save_pool(self, domain: str, sessions: list[SessionState]) -> None:
        path = self._pool_path(domain)
        path.write_text(
            json.dumps([session.model_dump(mode="json") for session in sessions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def acquire(self, url: str, current: SessionState | None = None, exclude_keys: set[str] | None = None) -> SessionState:
        domain = urlparse(url).netloc
        sessions = self._load_pool(domain)
        exclude_keys = exclude_keys or set()
        now = datetime.now()
        if current and current.session_key and not current.blocked and (current.cooldown_until is None or current.cooldown_until <= now):
            return current
        candidates = [
            session
            for session in sessions
            if not session.blocked
            and session.session_key not in exclude_keys
            and (session.cooldown_until is None or session.cooldown_until <= now)
        ]
        if candidates:
            candidates.sort(key=lambda session: (session.health_score, -session.consecutive_failures, session.updated_at), reverse=True)
            return candidates[0]
        return SessionState(session_key=str(uuid.uuid4())[:8], domain=domain)

    def release(self, url: str, session: SessionState, success: bool, status_code: int | None = None, error: str = "") -> SessionState:
        domain = urlparse(url).netloc
        session = session.model_copy(deep=True)
        session.last_status_code = status_code
        session.last_error = error
        session.updated_at = datetime.now()
        if success:
            session.health_score = min(1.0, session.health_score + 0.05)
            session.blocked = False
            session.blocked_reason = ""
            session.consecutive_failures = 0
            session.cooldown_until = None
        else:
            session.health_score = max(0.0, session.health_score - 0.2)
            session.consecutive_failures += 1
            session.cooldown_until = datetime.now() + timedelta(seconds=min(300, 10 * session.consecutive_failures))
            if status_code in {401, 403, 429}:
                session.blocked = True
                session.blocked_reason = f"HTTP {status_code}"
                session.cooldown_until = datetime.now() + timedelta(minutes=5)

        sessions = self._load_pool(domain)
        remaining = [item for item in sessions if item.session_key != session.session_key]
        remaining.append(session)
        self._save_pool(domain, remaining[-10:])
        return session
