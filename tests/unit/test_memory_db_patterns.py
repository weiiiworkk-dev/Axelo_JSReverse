from __future__ import annotations

from pathlib import Path

from axelo.memory.db import MemoryDB
from axelo.memory.schema import SitePattern


def test_get_site_pattern_ignores_unverified_records(tmp_path: Path):
    db = MemoryDB(tmp_path / "axelo.db")
    db.save_site_pattern(
        SitePattern(
            domain="lazada.com.my",
            algorithm_type="custom",
            verified=False,
            success_count=0,
        )
    )

    assert db.get_site_pattern("lazada.com.my") is None


def test_get_site_pattern_returns_verified_record(tmp_path: Path):
    db = MemoryDB(tmp_path / "axelo.db")
    db.save_site_pattern(
        SitePattern(
            domain="lazada.com.my",
            algorithm_type="mtop",
            verified=True,
            success_count=1,
        )
    )

    record = db.get_site_pattern("lazada.com.my")

    assert record is not None
    assert record.algorithm_type == "mtop"
