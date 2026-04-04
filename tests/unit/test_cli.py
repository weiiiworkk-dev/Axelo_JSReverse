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


def test_submit_reverse_uses_platform_runtime(monkeypatch):
    captured: dict = {}

    class FakeJob:
        job_id = "reverse-001"

    class FakeControl:
        def submit_reverse_job(self, spec):
            captured["spec"] = spec
            return FakeJob()

    class FakeRuntime:
        control = FakeControl()

    monkeypatch.setattr("axelo.cli._platform_runtime", lambda: FakeRuntime())

    result = runner.invoke(
        app,
        [
            "submit",
            "reverse",
            "https://example.com",
            "--goal",
            "demo",
        ],
    )

    assert result.exit_code == 0
    assert captured["spec"].url == "https://example.com"
    assert captured["spec"].goal == "demo"
    assert "reverse-001" in result.stdout


def test_frontier_seed_uses_platform_runtime(monkeypatch):
    captured: dict = {}

    class FakeItem:
        pass

    class FakeFrontier:
        def seed(self, request):
            captured["request"] = request
            return [FakeItem(), FakeItem()]

    class FakeRuntime:
        frontier = FakeFrontier()

    monkeypatch.setattr("axelo.cli._platform_runtime", lambda: FakeRuntime())

    result = runner.invoke(
        app,
        [
            "frontier",
            "seed",
            "https://example.com/a",
            "https://example.com/b",
        ],
    )

    assert result.exit_code == 0
    assert captured["request"].urls == ["https://example.com/a", "https://example.com/b"]
    assert "2" in result.stdout
