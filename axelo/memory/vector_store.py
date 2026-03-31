from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from typing import NamedTuple
import structlog

log = structlog.get_logger()


class SearchResult(NamedTuple):
    vector_id: int
    session_id: str
    score: float
    summary: str


class VectorStore:
    """
    FAISS 向量库，存储逆向经验的语义嵌入。
    使用 sentence-transformers 的轻量模型（all-MiniLM-L6-v2, 22MB）。
    懒加载：首次调用时初始化，不影响不需要向量功能的路径。
    """
    MODEL_NAME = "all-MiniLM-L6-v2"
    DIM = 384

    def __init__(self, index_dir: Path) -> None:
        self._dir = index_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = index_dir / "faiss.index"
        self._meta_path = index_dir / "meta.json"
        self._index = None
        self._model = None
        # {vector_id: {"session_id": ..., "summary": ...}}
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
                self._index = faiss.IndexFlatIP(self.DIM)  # Inner Product（余弦相似度）
            log.debug("vector_store_ready", entries=self._index.ntotal)
        except ImportError as e:
            log.warning("vector_store_unavailable", reason=str(e))

    def add(self, session_id: str, text: str) -> int | None:
        """将文本嵌入并加入索引，返回 vector_id"""
        self._lazy_init()
        if self._index is None:
            return None
        import faiss
        vec = self._encode(text)
        vector_id = self._index.ntotal
        self._index.add(vec)
        self._meta[vector_id] = {"session_id": session_id, "summary": text[:200]}
        self._save()
        return vector_id

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """语义搜索，返回最相似的会话记录"""
        self._lazy_init()
        if self._index is None or self._index.ntotal == 0:
            return []
        vec = self._encode(query)
        k = min(top_k, self._index.ntotal)
        scores, ids = self._index.search(vec, k)
        results = []
        for score, vid in zip(scores[0], ids[0]):
            if vid == -1:
                continue
            meta = self._meta.get(int(vid), {})
            results.append(SearchResult(
                vector_id=int(vid),
                session_id=meta.get("session_id", ""),
                score=float(score),
                summary=meta.get("summary", ""),
            ))
        return results

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
                return {int(k): v for k, v in raw.items()}
            except Exception:
                pass
        return {}
