"""
Sequential run ID allocator.

Stores a counter in workspace/run_counter.json and uses a companion .lock
file for cross-process safety on both Windows (msvcrt) and POSIX (fcntl).

Returns IDs of the form run_0001, run_0002, …, run_9999.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_COUNTER_FILE = "run_counter.json"
_LOCK_FILE = "run_counter.lock"


# ---------------------------------------------------------------------------
# Platform-specific file locking
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _acquire(fh) -> None:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            # Retry with blocking lock on Windows
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _release(fh) -> None:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl  # type: ignore[import]

    def _acquire(fh) -> None:  # type: ignore[misc]
        fcntl.flock(fh, fcntl.LOCK_EX)

    def _release(fh) -> None:  # type: ignore[misc]
        fcntl.flock(fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def allocate_run_id(workspace: Path) -> str:
    """
    Atomically increment the counter and return a run ID like ``run_0001``.

    Thread- and process-safe via an exclusive lock on a companion .lock file.
    The counter persists across restarts in *workspace/run_counter.json*.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    lock_path = workspace / _LOCK_FILE
    counter_path = workspace / _COUNTER_FILE

    with open(lock_path, "w") as lock_fh:
        _acquire(lock_fh)
        try:
            if counter_path.exists():
                data = json.loads(counter_path.read_text(encoding="utf-8"))
                current = int(data.get("counter", 0))
            else:
                current = 0
            next_count = current + 1
            counter_path.write_text(
                json.dumps({"counter": next_count}, indent=2),
                encoding="utf-8",
            )
        finally:
            _release(lock_fh)

    return f"run_{next_count:04d}"


def peek_next_run_id(workspace: Path) -> str:
    """Return what the *next* run ID would be without incrementing (for display)."""
    counter_path = workspace / _COUNTER_FILE
    if counter_path.exists():
        data = json.loads(counter_path.read_text(encoding="utf-8"))
        current = int(data.get("counter", 0))
    else:
        current = 0
    return f"run_{current + 1:04d}"
