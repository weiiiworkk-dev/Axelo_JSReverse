from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import structlog


@contextmanager
def session_context(session_id: str, target_url: str = "", **extra) -> Generator[None, None, None]:
    """Bind session info into structlog contextvars for the duration of the with block."""
    structlog.contextvars.bind_contextvars(
        session_id=session_id,
        target_url=target_url,
        **extra,
    )
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars("session_id", "target_url", *extra.keys())
