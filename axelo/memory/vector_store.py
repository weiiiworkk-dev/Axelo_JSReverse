from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import numpy as np
import structlog

log = structlog.get_logger()


class SearchResult(NamedTuple):
    vector_id: int
    session_id: str
    score: float
    summary: str


class VectorStore:
    MODEL_NAME = "all-MiniLM-L6-v2"
    DIM = 384

    def __init__(self, index_dir: Path) -> None:
        self._dir = index_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = index_dir / "faiss.index"
        self._meta_path = index_dir / "meta.json"
        self._index = None
        self._model = None
        self._meta: dict[int, dict] = self._load_meta()

    def _lazy_init(self) -> None:
        if self._index is not None:
            return
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.MODEL_NAME)
            if self._index_path.exists():
                self._index = faiss.read_index(str(self._index_path))
            else:
                self._index = faiss.IndexFlatIP(self.DIM)
            log.debug("vector_store_ready", entries=self._index.ntotal)
        except ImportError as exc:
            log.warning("vector_store_unavailable", reason=str(exc))

    def add(self, session_id: str, text: str) -> int | None:
        self._lazy_init()
        if self._index is None:
            return None
        vec = self._encode(text)
        vector_id = self._index.ntotal
        self._index.add(vec)
        self._meta[vector_id] = {"session_id": session_id, "summary": text[:200]}
        self._save()
        return vector_id

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        self._lazy_init()
        if self._index is None or self._index.ntotal == 0:
            return []
        vec = self._encode(query)
        k = min(top_k, self._index.ntotal)
        scores, ids = self._index.search(vec, k)
        results: list[SearchResult] = []
        for score, vector_id in zip(scores[0], ids[0]):
            if vector_id == -1:
                continue
            meta = self._meta.get(int(vector_id), {})
            results.append(
                SearchResult(
                    vector_id=int(vector_id),
                    session_id=meta.get("session_id", ""),
                    score=float(score),
                    summary=meta.get("summary", ""),
                )
            )
        return results

    def has_entries(self) -> bool:
        return bool(self._meta) or self._index_path.exists()

    def _encode(self, text: str) -> np.ndarray:
        vec = self._model.encode([text], normalize_embeddings=True)
        return vec.astype(np.float32)

    def _save(self) -> None:
        import faiss

        faiss.write_index(self._index, str(self._index_path))
        self._meta_path.write_text(json.dumps(self._meta, ensure_ascii=False), encoding="utf-8")

    def _load_meta(self) -> dict[int, dict]:
        if self._meta_path.exists():
            try:
                raw = json.loads(self._meta_path.read_text(encoding="utf-8"))
                return {int(key): value for key, value in raw.items()}
            except Exception:
                pass
        return {}
