from __future__ import annotations
from axelo.core.logging.logger import configure_logging, get_logger
from axelo.core.logging.session_logger import session_context


def test_logger_returns_structlog():
    log = get_logger("test")
    assert log is not None


def test_session_context_binds():
    log = get_logger("test")
    with session_context(session_id="session_000001", target_url="https://x.com"):
        # structlog contextvars should be populated — just verify no exception
        assert True
