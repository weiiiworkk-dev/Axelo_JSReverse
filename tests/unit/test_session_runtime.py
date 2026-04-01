from __future__ import annotations

from pathlib import Path

from axelo.browser.session_pool import SessionPool
from axelo.models.session_state import SessionState
from axelo.storage import SessionStateStore


def test_session_state_store_roundtrip(tmp_path):
    store = SessionStateStore(tmp_path)
    state = SessionState(session_key="abc123", domain="example.com", storage_state_path="state.json")
    store.save("s01", state)
    loaded = store.load("s01")
    assert loaded is not None
    assert loaded.session_key == "abc123"


def test_session_pool_marks_blocked(tmp_path):
    pool = SessionPool(tmp_path)
    session = pool.acquire("https://example.com/path")
    updated = pool.release("https://example.com/path", session, success=False, status_code=403, error="blocked")
    assert updated.blocked is True
    assert updated.blocked_reason == "HTTP 403"
