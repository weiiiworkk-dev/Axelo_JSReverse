from __future__ import annotations

from pathlib import Path

from axelo.config import Settings


def test_settings_resolve_relative_workspace_and_sessions_root_to_project_root():
    cfg = Settings(
        workspace="workspace",
        sessions_root="workspace/sessions",
    )

    assert cfg.workspace.is_absolute()
    assert cfg.sessions_dir.is_absolute()
    assert cfg.sessions_dir == cfg.workspace / "sessions"


def test_settings_default_sessions_dir_stays_under_workspace():
    cfg = Settings(workspace="workspace", sessions_root=None)

    assert cfg.sessions_dir == cfg.workspace / "sessions"
    assert cfg.sessions_dir.parts[-2:] == ("workspace", "sessions")
