from __future__ import annotations
from axelo.agents.base import BaseAgent
from axelo.memory.writer import MemoryWriter
from axelo.models.analysis import AnalysisResult, AIHypothesis
from axelo.models.target import TargetSite
from axelo.cost.tracker import CostRecord
import structlog

log = structlog.get_logger()


class MemoryWriterAgent(BaseAgent):
    """
    记忆写入角色：在会话结束后将经验写入记忆库。
    只写入验证成功（或置信度 >= 0.8）的记录。
    不调用 AI（纯数据写入操作）。
    """
    role = "memory_writer"

    def __init__(self, *args, writer: MemoryWriter, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._writer = writer

    async def write(
        self,
        session_id: str,
        target: TargetSite,
        analysis: AnalysisResult,
        hypothesis: AIHypothesis | None,
        cost: CostRecord,
        verified: bool,
    ) -> None:
        # 质量门控：未验证且置信度低的不写入
        if not verified and (hypothesis is None or hypothesis.confidence < 0.75):
            log.info("memory_write_skipped", reason="未验证且置信度不足", session_id=session_id)
            return

        self._writer.write_session(
            session_id=session_id,
            target=target,
            analysis=analysis,
            hypothesis=hypothesis,
            cost=cost,
            verified=verified,
        )

        # 写入 Bundle 缓存（无论是否验证，静态分析结果可复用）
        for bid, sa in analysis.static.items():
            if sa.token_candidates:
                import json
                self._writer.write_bundle_cache(
                    content_hash=bid,
                    analysis_json=sa.model_dump_json(),
                    bundle_type="unknown",
                    algorithm_type=sa.token_candidates[0].token_type if sa.token_candidates else "unknown",
                    token_candidate_count=len(sa.token_candidates),
                    crypto_primitives=sa.crypto_imports[:5],
                )

        log.info("memory_written", session_id=session_id, verified=verified)
