from __future__ import annotations
import json
from axelo.memory.db import MemoryDB
from axelo.memory.vector_store import VectorStore
from axelo.memory.schema import ReverseSession, SitePattern, JSBundleCache
from axelo.models.analysis import AnalysisResult, AIHypothesis
from axelo.models.target import TargetSite
from axelo.cost.tracker import CostRecord
from axelo.utils.domain import extract_site_domain
import structlog

log = structlog.get_logger()


class MemoryWriter:
    """
    将本次逆向会话的经验写入记忆库。
    只在会话成功验证后写入，避免噪声污染经验库。
    """

    def __init__(self, db: MemoryDB, vector_store: VectorStore) -> None:
        self._db = db
        self._vs = vector_store

    def write_session(
        self,
        session_id: str,
        target: TargetSite,
        analysis: AnalysisResult,
        hypothesis: AIHypothesis | None,
        cost: CostRecord,
        verified: bool,
    ) -> None:
        domain = _extract_domain(target.url)

        # 构建经验摘要文本（用于向量嵌入）
        summary_parts = [
            f"域名: {domain}",
            f"目标: {target.interaction_goal}",
        ]
        if hypothesis:
            summary_parts.append(f"算法: {hypothesis.algorithm_description[:200]}")
            summary_parts.append(f"步骤: {' → '.join(hypothesis.steps[:4])}")
        if analysis.dynamic:
            summary_parts.append(f"加密原语: {', '.join(analysis.dynamic.crypto_primitives)}")

        experience_summary = "\n".join(summary_parts)

        # 构建静态特征摘要
        static_features: dict = {}
        for bid, sa in analysis.static.items():
            static_features[bid] = {
                "crypto_imports": sa.crypto_imports[:5],
                "env_access": sa.env_access[:5],
                "candidate_count": len(sa.token_candidates),
            }

        record = ReverseSession(
            session_id=session_id,
            url=target.url,
            domain=domain,
            goal=target.interaction_goal,
            difficulty=_estimate_difficulty(hypothesis, analysis),
            algorithm_type=hypothesis.algorithm_description[:50] if hypothesis else "unknown",
            codegen_strategy=hypothesis.codegen_strategy if hypothesis else "",
            ai_confidence=hypothesis.confidence if hypothesis else 0.0,
            verified=verified,
            total_cost_usd=cost.total_usd,
            total_tokens=cost.total_tokens,
            experience_summary=experience_summary,
            static_features=json.dumps(static_features, ensure_ascii=False),
            hook_trace_summary=_format_hook_summary(analysis),
            hypothesis_json=hypothesis.model_dump_json() if hypothesis else "",
        )

        self._db.save_session(record)

        # 写入向量库（仅验证成功的经验）
        if verified:
            vid = self._vs.add(session_id, experience_summary)
            log.info("memory_written", session_id=session_id, verified=verified, vector_id=vid)

        # 更新站点模式统计
        self._db.update_pattern_stats(domain, verified)

        # 如果是新站点，自动创建/更新站点模式记录
        if verified and hypothesis and not self._db.get_site_pattern(domain):
            pattern = SitePattern(
                domain=domain,
                algorithm_type=_infer_algo_type(hypothesis),
                difficulty=_estimate_difficulty(hypothesis, analysis),
                verified=verified,
                success_count=1 if verified else 0,
                notes=hypothesis.notes[:200] if hypothesis.notes else "",
            )
            self._db.save_site_pattern(pattern)

    def write_bundle_cache(
        self,
        content_hash: str,
        analysis_json: str,
        bundle_type: str,
        algorithm_type: str,
        token_candidate_count: int,
        crypto_primitives: list[str],
    ) -> None:
        cache = JSBundleCache(
            content_hash=content_hash,
            bundle_type=bundle_type,
            algorithm_type=algorithm_type,
            token_candidate_count=token_candidate_count,
            crypto_primitives=json.dumps(crypto_primitives),
            analysis_json=analysis_json,
        )
        self._db.save_bundle_cache(cache)
        log.debug("bundle_cache_written", hash=content_hash)


def _extract_domain(url: str) -> str:
    return extract_site_domain(url)


def _estimate_difficulty(hypothesis: AIHypothesis | None, analysis: AnalysisResult) -> str:
    if hypothesis is None:
        return "unknown"
    if hypothesis.python_feasibility >= 0.85 and hypothesis.confidence >= 0.8:
        return "medium"
    if analysis.dynamic and analysis.dynamic.crypto_primitives:
        return "hard"
    if hypothesis.codegen_strategy == "js_bridge":
        return "hard"
    return "medium"


def _infer_algo_type(hypothesis: AIHypothesis) -> str:
    desc = hypothesis.algorithm_description.lower()
    for kw, t in [("hmac", "hmac"), ("rsa", "rsa"), ("aes", "aes"), ("md5", "md5"),
                  ("fingerprint", "fingerprint"), ("canvas", "fingerprint")]:
        if kw in desc:
            return t
    return "custom"


def _format_hook_summary(analysis: AnalysisResult) -> str:
    if not analysis.dynamic:
        return ""
    parts = analysis.dynamic.crypto_primitives[:5]
    return ", ".join(parts)
