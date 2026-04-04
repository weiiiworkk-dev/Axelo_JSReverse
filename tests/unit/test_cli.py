from __future__ import annotations

from typer.testing import CliRunner

from axelo.browser.profiles import PROFILES
from axelo.cli import app
from axelo.orchestrator.master import MasterResult


runner = CliRunner()


def test_run_profile_and_seed_are_forwarded(monkeypatch):
    captured: dict = {}

    class FakeMasterOrchestrator:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return MasterResult(
                session_id="cli01",
                url=kwargs["url"],
                completed=True,
            )

    monkeypatch.setattr("axelo.cli.MasterOrchestrator", FakeMasterOrchestrator)

    original_seed = PROFILES["default"].interaction_simulation.pointer.default_seed
    result = runner.invoke(
        app,
        [
            "run",
            "https://example.com",
            "--profile",
            "default",
            "--seed",
            "2024",
        ],
    )

    assert result.exit_code == 0
    assert captured["browser_profile"].interaction_simulation.pointer.default_seed == 2024
    assert PROFILES["default"].interaction_simulation.pointer.default_seed == original_seed


def test_run_rejects_unknown_profile():
    result = runner.invoke(
        app,
        [
            "run",
            "https://example.com",
            "--profile",
            "missing-profile",
        ],
    )

    assert result.exit_code == 2
    assert "missing-profile" in result.stdout
