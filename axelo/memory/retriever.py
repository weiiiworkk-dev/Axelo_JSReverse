from __future__ import annotations
from urllib.parse import urlparse
from axelo.memory.db import MemoryDB
from axelo.memory.vector_store import VectorStore
from axelo.memory.schema import SitePattern, SolutionTemplate, ReverseSession
import structlog

log = structlog.get_logger()


class BM25Index:
    """
    轻量 BM25 关键词索引，用于检索相似的历史逆向经验。
    懒加载：首次 search() 时构建索引。
    """

    def __init__(self) -> None:
        self._docs: list[dict] = []       # {"id": session_id, "text": corpus_text}
        self._bm25 = None
        self._dirty = True

    def add(self, session_id: str, text: str) -> None:
        self._docs.append({"id": session_id, "text": text})
        self._dirty = True

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """返回 [(session_id, score), ...]"""
        if not self._docs:
            return []
        self._build_if_needed()
        from rank_bm25 import BM25Okapi
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            ((self._docs[i]["id"], float(scores[i])) for i in range(len(self._docs))),
            key=lambda x: -x[1],
        )
        return [r for r in ranked[:top_k] if r[1] > 0]

    def _build_if_needed(self) -> None:
        if not self._dirty:
            return
        from rank_bm25 import BM25Okapi
        corpus = [_tokenize(d["text"]) for d in self._docs]
        self._bm25 = BM25Okapi(corpus)
        self._dirty = False


def _tokenize(text: str) -> list[str]:
    """简单分词：小写 + 按非字母数字切分"""
    import re
    return re.findall(r'[a-z0-9]+', text.lower())


class MemoryRetriever:
    """
    三层混合检索器：
    1. 精确匹配（域名 + 算法类型）→ SQL
    2. BM25 关键词检索（技术术语：hmac/sha256/canvas/wbi 等）→ rank-bm25
    3. 向量语义相似度（整体经验描述）→ FAISS

    三层结果融合后去重，按综合得分排序。
    """

    def __init__(self, db: MemoryDB, vector_store: VectorStore) -> None:
        self._db = db
        self._vs = vector_store
        self._bm25 = BM25Index()
        self._bm25_loaded = False

    def _ensure_bm25(self) -> None:
        """首次调用时，从数据库加载所有已验证会话到 BM25 索引"""
        if self._bm25_loaded:
            return
        sessions = self._db.get_similar_sessions("")
        for s in sessions:
            if s.experience_summary:
                self._bm25.add(s.session_id, s.experience_summary)
        self._bm25_loaded = True

    def add_to_bm25(self, session_id: str, text: str) -> None:
        """写入新经验时同步更新 BM25 索引"""
        self._bm25.add(session_id, text)

    def query_for_url(self, url: str, query_text: str = "") -> dict:
        """
        三层检索，返回：
        - known_pattern: 已知站点模式
        - similar_sessions: 相似历史经验（去重合并）
        - suggested_templates: 推荐解法模板
        - bm25_hits: BM25 关键词命中摘要
        """
        domain = _extract_domain(url)

        # 1. 精确 SQL 匹配
        pattern = self._db.get_site_pattern(domain)
        sql_sessions = self._db.get_similar_sessions(domain)

        # 2. BM25 关键词检索
        bm25_sessions: list[ReverseSession] = []
        bm25_hits: list[str] = []
        if query_text:
            self._ensure_bm25()
            bm25_results = self._bm25.search(f"{domain} {query_text}", top_k=5)
            for sid, score in bm25_results:
                if score > 0.1:
                    rows = self._db.get_similar_sessions(domain)
                    for r in rows:
                        if r.session_id == sid:
                            bm25_sessions.append(r)
                            bm25_hits.append(f"{sid}(bm25={score:.2f})")
                            break

        # 3. 向量语义检索
        vec_sessions: list[ReverseSession] = []
        if query_text and self._vs._index is not None:
            vec_results = self._vs.search(f"{domain} {query_text}", top_k=3)
            for vr in vec_results:
                if vr.score > 0.6:
                    rows = self._db.get_similar_sessions(domain)
                    for r in rows:
                        if r.session_id == vr.session_id:
                            vec_sessions.append(r)
                            break

        # 融合去重（SQL > BM25 > 向量）
        seen: set[str] = set()
        merged: list[ReverseSession] = []
        for s in sql_sessions + bm25_sessions + vec_sessions:
            if s.session_id not in seen:
                seen.add(s.session_id)
                merged.append(s)

        # 推荐模板
        algo_hint = pattern.algorithm_type if pattern else "hmac"
        templates = self._db.list_templates(algo_hint)

        result = {
            "domain": domain,
            "known_pattern": pattern.model_dump() if pattern else None,
            "similar_sessions": [s.model_dump() for s in merged[:3]],
            "suggested_templates": [t.model_dump() for t in templates[:2]],
            "difficulty_hint": pattern.difficulty if pattern else None,
            "bm25_hits": bm25_hits,
        }

        log.info(
            "memory_query",
            domain=domain,
            has_pattern=pattern is not None,
            sql_hits=len(sql_sessions),
            bm25_hits=len(bm25_sessions),
            vec_hits=len(vec_sessions),
        )
        return result

    def get_template(self, name: str) -> SolutionTemplate | None:
        return self._db.get_template_by_name(name)

    def get_all_templates(self) -> list[SolutionTemplate]:
        return self._db.list_templates()

    def bm25_search_templates(self, query: str) -> list[SolutionTemplate]:
        """用 BM25 搜索最相关的解法模板"""
        templates = self._db.list_templates()
        if not templates:
            return []
        from rank_bm25 import BM25Okapi
        corpus = [_tokenize(f"{t.name} {t.description} {t.algorithm_type}") for t in templates]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(templates)), key=lambda i: -scores[i])
        return [templates[i] for i in ranked[:3] if scores[i] > 0]


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return url[:50]
