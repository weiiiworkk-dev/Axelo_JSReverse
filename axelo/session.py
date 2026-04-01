from __future__ import annotations
import uuid
from pathlib import Path
import structlog

from axelo.config import settings
from axelo.models.pipeline import PipelineState
from axelo.models.target import TargetSite, BrowserProfile
from axelo.modes.registry import create_mode
from axelo.storage.session_store import SessionStore
from axelo.js_tools.runner import NodeRunner
from axelo.analysis.static.ast_analyzer import ASTAnalyzer
from axelo.ai.client import AIClient
from axelo.pipeline.orchestrator import PipelineOrchestrator
from axelo.pipeline.stages import (
    CrawlStage, FetchStage, DeobfuscateStage, StaticAnalysisStage,
    DynamicAnalysisStage, AIAnalysisStage, CodeGenStage, VerifyStage,
)

log = structlog.get_logger()


class EngineSession:
    """
    顶层会话管理器：组装所有依赖，启动完整流水线。
    """

    def __init__(self) -> None:
        self._store = SessionStore(settings.sessions_dir)

    async def run(
        self,
        url: str,
        goal: str,
        mode_name: str = "interactive",
        session_id: str | None = None,
        resume: bool = False,
        known_endpoint: str = "",
        antibot_type: str = "unknown",
        requires_login: bool | None = None,
        output_format: str = "print",
        crawl_rate: str = "standard",
    ) -> PipelineState:
        sid = session_id or str(uuid.uuid4())[:8]
        mode = create_mode(mode_name)

        # 加载或新建 PipelineState
        state = None
        if resume and session_id:
            state = self._store.load(session_id)
            if state:
                log.info("session_resumed", session_id=sid)
            else:
                log.warning("session_not_found", session_id=sid)

        if state is None:
            state = PipelineState(session_id=sid, mode=mode_name)

        # 构建目标站点
        target = TargetSite(
            url=url,
            session_id=sid,
            interaction_goal=goal,
            browser_profile=BrowserProfile(),
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
        )

        # 启动 Node.js 运行器
        runner = NodeRunner(settings.node_bin)
        await runner.start()

        try:
            # 构建 AI 客户端
            ai_client = AIClient(
                api_key=settings.anthropic_api_key,
                model=settings.model,
            )

            # 组装分析器
            ast_analyzer = ASTAnalyzer(runner)

            # 组装流水线
            stages = [
                CrawlStage(),
                FetchStage(),
                DeobfuscateStage(runner),
                StaticAnalysisStage(ast_analyzer),
                DynamicAnalysisStage(),
                AIAnalysisStage(ai_client),
                CodeGenStage(ai_client),
                VerifyStage(),
            ]

            orchestrator = PipelineOrchestrator(stages, self._store)
            state = await orchestrator.run(state, mode, target=target)

        finally:
            await runner.stop()

        return state

    def switch_mode(self, state: PipelineState, new_mode: str) -> None:
        """会话中途切换模式"""
        state.mode = new_mode
        self._store.save(state)
        log.info("mode_switched", new_mode=new_mode)

    def list_sessions(self) -> list[str]:
        return self._store.list_sessions()
