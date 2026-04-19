from __future__ import annotations
import json
from pathlib import Path
import pytest
from axelo.core.artifacts.manager import ArtifactSessionManager
from axelo.core.artifacts.writer import ArtifactWriter


def test_first_session_is_000001(tmp_path):
    mgr = ArtifactSessionManager(artifacts_root=tmp_path)
    sid = mgr.create_session()
    assert sid == "session_000001"
    assert (tmp_path / "session_000001").is_dir()


def test_second_session_increments(tmp_path):
    mgr = ArtifactSessionManager(artifacts_root=tmp_path)
    mgr.create_session()
    sid2 = mgr.create_session()
    assert sid2 == "session_000002"


def test_session_subdirs_created(tmp_path):
    mgr = ArtifactSessionManager(artifacts_root=tmp_path)
    sid = mgr.create_session()
    session_path = tmp_path / sid
    for sub in ["logs", "recon", "browser", "analysis", "codegen", "verification", "replay", "final"]:
        assert (session_path / sub).is_dir()


def test_writer_writes_json(tmp_path):
    writer = ArtifactWriter(session_path=tmp_path / "session_000001")
    (tmp_path / "session_000001" / "recon").mkdir(parents=True)
    writer.write_json("recon/site_profile.json", {"antibot": "cloudflare"})
    data = json.loads((tmp_path / "session_000001" / "recon" / "site_profile.json").read_text())
    assert data["antibot"] == "cloudflare"


def test_writer_appends_jsonl(tmp_path):
    writer = ArtifactWriter(session_path=tmp_path / "session_000001")
    (tmp_path / "session_000001" / "logs").mkdir(parents=True)
    writer.append_jsonl("logs/state_transitions.jsonl", {"from": "INIT", "to": "PLANNING"})
    writer.append_jsonl("logs/state_transitions.jsonl", {"from": "PLANNING", "to": "RUNNING"})
    lines = (tmp_path / "session_000001" / "logs" / "state_transitions.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
