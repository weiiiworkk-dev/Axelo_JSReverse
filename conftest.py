"""
Root conftest — stub out modules that are missing in this worktree
so that imports of axelo.config (and transitively axelo.ai) succeed.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _stub_if_missing(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


for _mod in [
    "axelo.js_tools",
    "axelo.patterns",
]:
    _stub_if_missing(_mod)
