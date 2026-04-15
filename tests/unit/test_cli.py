from __future__ import annotations

from typer.testing import CliRunner

from axelo.browser.profiles import PROFILES
from axelo.chat.cli import AxeloChatCLI
from axelo.cli import app
from axelo.engine.models import RequirementSheet


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


def test_cli_requirement_helpers_normalize_and_infer():
    assert AxeloChatCLI._normalize_url("example.com") == "https://example.com"
    assert AxeloChatCLI._parse_item_limit("200 items") == 200
    assert AxeloChatCLI._infer_fields("crawl product listing") == [
        "title",
        "price",
        "rating",
        "review_count",
        "url",
    ]


def test_requirement_sheet_builds_checklist_and_prompt():
    sheet = RequirementSheet(
        target_url="https://example.com",
        objective="crawl product listing",
        target_scope="search keyword iphone",
        fields=["title", "price", "url"],
        item_limit=120,
        constraints="respect rate limit",
    )

    checklist = sheet.checklist()
    assert checklist[0] == "Target URL: https://example.com"
    assert "Fields: title, price, url" in checklist
    assert "Requirement checklist for this run:" in sheet.to_prompt()
    assert sheet.to_metadata()["item_limit"] == 120
