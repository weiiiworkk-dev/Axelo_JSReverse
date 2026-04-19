"""
Conftest for axelo.ai tests.

This worktree may be missing some sibling modules (js_tools, patterns, etc.)
that are imported transitively via axelo.utils.__init__. We stub them out
before any test module is collected so the import chain succeeds.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


def _stub_if_missing(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


# Modules that don't exist in this worktree but are pulled in transitively
for _mod in [
    "axelo.js_tools",
    "axelo.patterns",
]:
    _stub_if_missing(_mod)
