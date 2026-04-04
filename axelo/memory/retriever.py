from __future__ import annotations

import re
from urllib.parse import urlparse

import structlog

from axelo.memory.db import MemoryDB
from axelo.memory.schema import ReverseSession, SitePattern, SolutionTemplate
from axelo.memory.vector_store import VectorStore

log = structlog.get_logger()


class BM25Index:
    def __init__(self) -> None:
        self._docs: list[dict[str, str]] = []
        self._bm25 = None
        self._dirty = True

    def add(self, session_id: str, text: str) -> None:
        self._docs.append({"id": session_id, "text": text})
        self._dirty = True

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        if not self._docs:
            return []
        self._build_if_needed()
        query_tokens = _tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(
            ((self._docs[index]["id"], float(scores[index])) for index in range(len(self._docs))),
            key=lambda item: -item[1],
        )
        positive = [item for item in ranked[:top_k] if item[1] > 0]
        if positive:
            return positive

        fallback_ranked = sorted(
            (
                (
                    item["id"],
                    float(len(set(query_tokens) & set(_tokenize(item["text"])))),
                )
                for item in self._docs
            ),
            key=lambda entry: -entry[1],
        )
        return [item for item in fallback_ranked[:top_k] if item[1] > 0]

    def _build_if_needed(self) -> None:
        if not self._dirty:
            return
        from rank_bm25 import BM25Okapi

        corpus = [_tokenize(item["text"]) for item in self._docs]
        self._bm25 = BM25Okapi(corpus)
        self._dirty = False


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class MemoryRetriever:
    def __init__(self, db: MemoryDB, vector_store: VectorStore) -> None:
        self._db = db
        self._vs = vector_store
        self._bm25 = BM25Index()
        self._bm25_loaded = False

    def _ensure_bm25(self) -> None:
        if self._bm25_loaded:
            return
        for session in self._db.list_verified_sessions():
            if session.experience_summary:
                self._bm25.add(session.session_id, session.experience_summary)
        self._bm25_loaded = True

    def add_to_bm25(self, session_id: str, text: str) -> None:
        self._bm25.add(session_id, text)

    def query_for_url(self, url: str, query_text: str = "") -> dict:
        domain = _extract_domain(url)

        pattern = self._db.get_site_pattern(domain)
        sql_sessions = self._db.get_similar_sessions(domain)

        bm25_sessions: list[ReverseSession] = []
        bm25_hits: list[str] = []
        if query_text:
            self._ensure_bm25()
            bm25_scores = {
                session_id: score
                for session_id, score in self._bm25.search(f"{domain} {query_text}", top_k=5)
                if score > 0.1
            }
            bm25_sessions = self._hydrate_sessions(list(bm25_scores))
            bm25_hits = [
                f"{session.session_id}(bm25={bm25_scores[session.session_id]:.2f})"
                for session in bm25_sessions
                if session.session_id in bm25_scores
            ]

        vec_sessions: list[ReverseSession] = []
        if query_text and self._vs.has_entries():
            vec_results = self._vs.search(f"{domain} {query_text}", top_k=3)
            vec_sessions = self._hydrate_sessions(
                [item.session_id for item in vec_results if item.score > 0.6]
            )

        seen: set[str] = set()
        merged: list[ReverseSession] = []
        for session in sql_sessions + bm25_sessions + vec_sessions:
            if session.session_id not in seen:
                seen.add(session.session_id)
                merged.append(session)

        algo_hint = pattern.algorithm_type if pattern else "hmac"
        templates = self._db.list_templates(algo_hint)

        log.info(
            "memory_query",
            domain=domain,
            has_pattern=pattern is not None,
            sql_hits=len(sql_sessions),
            bm25_hits=len(bm25_sessions),
            vec_hits=len(vec_sessions),
        )
        return {
            "domain": domain,
            "known_pattern": pattern.model_dump() if pattern else None,
            "similar_sessions": [session.model_dump() for session in merged[:3]],
            "suggested_templates": [template.model_dump() for template in templates[:2]],
            "difficulty_hint": pattern.difficulty if pattern else None,
            "bm25_hits": bm25_hits,
        }

    def get_template(self, name: str) -> SolutionTemplate | None:
        return self._db.get_template_by_name(name)

    def get_all_templates(self) -> list[SolutionTemplate]:
        return self._db.list_templates()

    def bm25_search_templates(self, query: str) -> list[SolutionTemplate]:
        templates = self._db.list_templates()
        if not templates:
            return []

        from rank_bm25 import BM25Okapi

        corpus = [_tokenize(f"{template.name} {template.description} {template.algorithm_type}") for template in templates]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(templates)), key=lambda index: -scores[index])
        return [templates[index] for index in ranked[:3] if scores[index] > 0]

    def _hydrate_sessions(self, session_ids: list[str]) -> list[ReverseSession]:
        return self._db.get_sessions_by_ids(session_ids)


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return url[:50]
