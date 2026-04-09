from __future__ import annotations

import json
import sys
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
            import logging as _logging
            import os

            # Suppress verbose output from HuggingFace / transformers / faiss
            # before importing the heavy libraries.
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "true")
            os.environ.setdefault("HF_HUB_VERBOSITY", "error")
            os.environ.setdefault("TQDM_DISABLE", "1")  # suppress all tqdm progress bars
            for _noisy in (
                "transformers", "transformers.modeling_utils",
                "transformers.tokenization_utils_base",
                "transformers.configuration_utils",
                "sentence_transformers",
                "huggingface_hub", "huggingface_hub.utils._validators",
                "huggingface_hub.file_download",
                "faiss", "faiss.loader",
                "httpx", "httpcore",
                "filelock",
            ):
                _logging.getLogger(_noisy).setLevel(_logging.WARNING)

            import faiss
            from sentence_transformers import SentenceTransformer

            # Suppress transformers' per-weight load reports and all advisory output
            try:
                import transformers
                transformers.logging.set_verbosity_error()
            except Exception:
                pass
            try:
                import huggingface_hub.utils._headers as _hf_headers
                # Silence the unauthenticated-request warning that hits stderr
                _logging.getLogger("huggingface_hub.utils._headers").setLevel(_logging.ERROR)
            except Exception:
                pass

            # Redirect both Python-level and OS-level stdout/stderr during model
            # loading to suppress print()-based load reports (e.g. BertModel
            # LOAD REPORT) that bypass the logging system.
            import io
            _null_fd = os.open(os.devnull, os.O_WRONLY)
            _saved = {}
            for _fd in (1, 2):
                _saved[_fd] = os.dup(_fd)
                os.dup2(_null_fd, _fd)
            _old_stdout, _old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = io.StringIO()
                sys.stderr = io.StringIO()
                self._model = SentenceTransformer(self.MODEL_NAME)
            finally:
                sys.stdout = _old_stdout
                sys.stderr = _old_stderr
                for _fd, _saved_fd in _saved.items():
                    os.dup2(_saved_fd, _fd)
                    os.close(_saved_fd)
                os.close(_null_fd)
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
        vec = self._model.encode([text], normalize_embeddings=True, show_progress_bar=False)
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
