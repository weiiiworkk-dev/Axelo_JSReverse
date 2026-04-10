from __future__ import annotations

from typer.testing import CliRunner

from axelo.browser.profiles import PROFILES
from axelo.cli import app


runner = CliRunner()


def test_run_profile_and_seed_are_forwarded(monkeypatch):
    captured: dict = {}

    class FakeChatCLI:
        async def _run_non_interactive(self, url: str, goal: str):
            captured["url"] = url
            captured["goal"] = goal

    monkeypatch.setattr("axelo.chat.cli.AxeloChatCLI", FakeChatCLI)

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
    assert captured["url"] == "https://example.com"
    assert isinstance(captured["goal"], str)
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


def test_tools_command_runs():
    result = runner.invoke(app, ["tools"])
    assert result.exit_code == 0
