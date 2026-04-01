from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import BrowserContext

from axelo.models.session_state import SessionState
from axelo.storage import SessionStateStore


class BrowserStateStore:
    def __init__(self, store: SessionStateStore) -> None:
        self._store = store

    async def persist_context(self, session_id: str, domain: str, context: BrowserContext, state: SessionState) -> SessionState:
        storage_path = self._store.browser_storage_path(session_id)
        await context.storage_state(path=str(storage_path))
        cookies = await context.cookies()
        updated = state.model_copy(deep=True)
        updated.domain = urlparse(domain).netloc or domain
        updated.storage_state_path = str(storage_path)
        updated.cookies = cookies
        updated.reuse_count += 1
        updated.last_used_at = datetime.now()
        updated.updated_at = datetime.now()
        self._store.save(session_id, updated)
        return updated
