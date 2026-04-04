from __future__ import annotations

from axelo.memory.db import MemoryDB
from axelo.memory.retriever import MemoryRetriever
from axelo.memory.schema import ReverseSession
from axelo.memory.vector_store import SearchResult, VectorStore


def _save_session(db: MemoryDB, *, session_id: str, domain: str, summary: str) -> None:
    db.save_session(
        ReverseSession(
            session_id=session_id,
            url=f"https://{domain}/api",
            domain=domain,
            goal="demo",
            difficulty="medium",
            algorithm_type="hmac",
            verified=True,
            ai_confidence=0.9,
            experience_summary=summary,
        )
    )


def test_query_for_url_uses_global_verified_sessions_for_bm25(tmp_path):
    db = MemoryDB(tmp_path / "memory.db")
    vs = VectorStore(tmp_path / "vectors")
    retriever = MemoryRetriever(db, vs)

    _save_session(db, session_id="global-hmac", domain="legacy.example", summary="hmac sha256 timestamp sign flow")
    _save_session(db, session_id="other-flow", domain="other.example", summary="rsa signature exchange flow")

    result = retriever.query_for_url("https://brand-new.example/api", "need hmac timestamp sign")

    session_ids = [item["session_id"] for item in result["similar_sessions"]]
    assert "global-hmac" in session_ids
    assert any(hit.startswith("global-hmac") for hit in result["bm25_hits"])


def test_query_for_url_hydrates_vector_hits_by_session_id(tmp_path, monkeypatch):
    db = MemoryDB(tmp_path / "memory.db")
    vs = VectorStore(tmp_path / "vectors")
    retriever = MemoryRetriever(db, vs)

    _save_session(db, session_id="vector-hit", domain="other.example", summary="canvas fingerprint bridge flow")

    monkeypatch.setattr(
        vs,
        "search",
        lambda query, top_k=3: [SearchResult(vector_id=1, session_id="vector-hit", score=0.91, summary="fingerprint")],
    )

    result = retriever.query_for_url("https://fresh.example/api", "canvas webgl fingerprint")

    session_ids = [item["session_id"] for item in result["similar_sessions"]]
    assert "vector-hit" in session_ids
