from __future__ import annotations
from pydantic import BaseModel, Field
from axelo.agents.base import BaseAgent
from axelo.models.analysis import StaticAnalysis
from axelo.models.target import TargetSite
import structlog

log = structlog.get_logger()


class ScanReport(BaseModel):
    """Scanner 输出：快速 bundle 特征扫描结果"""
    bundle_complexity: str = Field(description="bundle 复杂度评估：simple/moderate/complex/obfuscated")
    detected_frameworks: list[str] = Field(default_factory=list, description="检测到的 JS 框架/库")
    crypto_libs: list[str] = Field(default_factory=list, description="检测到的加密库")
    interesting_functions: list[str] = Field(default_factory=list, description="值得深入分析的函数名/ID，最多8个")
    token_field_hints: list[str] = Field(default_factory=list, description="疑似 token 字段的请求头名称")
    priority_bundles: list[str] = Field(default_factory=list, description="最应优先分析的 bundle_id 列表")
    quick_verdict: str = Field(description="快速判断：是否值得继续深入分析，以及理由（2句话）")
    estimated_difficulty: str = Field(description="预估难度：easy/medium/hard/extreme")


SCANNER_SYSTEM = """你是一位 JS 逆向扫描器（Scanner）。
你的工作是**快速、高效**地扫描 JS bundle 特征，给出第一印象评估。
你不需要完整逆向，只需：
1. 识别关键加密库和模式
2. 标记值得深入分析的函数
3. 预估难度和优先级

## BM25 关键词检索命中的相似模板（供参考）
{bm25_context}

保持简洁，不要深入分析细节。"""


class ScannerAgent(BaseAgent):
    """
    快速扫描 bundle 特征，输出结构化扫描报告。
    使用 Haiku（最便宜模型）+ BM25 关键词预检索，减少 AI 调用成本。

    BM25 检索流程：
    1. 从 static_results 提取关键词（crypto_imports, env_access, 候选函数类型）
    2. BM25 搜索最相关的历史模板
    3. 将命中模板摘要注入 Scanner prompt，帮助 AI 快速定位算法类型
    """
    role = "scanner"
    default_model = "claude-haiku-4-5"

    def __init__(self, *args, retriever=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever  # 可选，有则启用 BM25

    async def scan(
        self,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
    ) -> ScanReport:
        # ── BM25 预检索（纯本地，零成本）──────────────────────────
        bm25_context = self._bm25_lookup(static_results)

        # ── 构建紧凑 AI 上下文 ────────────────────────────────────
        parts = [f"URL: {target.url}", f"目标: {target.interaction_goal}", ""]

        for bid, sa in static_results.items():
            parts.append(f"Bundle {bid}:")
            parts.append(f"  加密API: {sa.crypto_imports[:5]}")
            parts.append(f"  环境访问: {sa.env_access[:5]}")
            parts.append(f"  候选函数数: {len(sa.token_candidates)}")
            if sa.token_candidates:
                top = sa.token_candidates[0]
                parts.append(f"  最高置信候选: {top.func_id} ({top.token_type}, {top.confidence:.0%})")
            if sa.string_constants:
                parts.append(f"  关键字符串: {sa.string_constants[:3]}")

        context = "\n".join(parts)
        system_prompt = SCANNER_SYSTEM.format(bm25_context=bm25_context)

        client = self._build_client()
        result = await client.analyze(
            system_prompt=system_prompt,
            user_message=f"请扫描以下 JS bundle 特征：\n\n{context}",
            output_schema=ScanReport,
            tool_name="scan_report",
            max_tokens=2048,
        )

        self._cost.add_ai_call(
            model=self._select_model(),
            input_tok=len(context) // 4,
            output_tok=200,
            stage="scanner",
        )

        log.info(
            "scanner_done",
            difficulty=result.estimated_difficulty,
            interesting=len(result.interesting_functions),
            bm25_used=bool(bm25_context.strip()),
        )
        return result

    def _bm25_lookup(self, static_results: dict[str, StaticAnalysis]) -> str:
        """
        从静态分析结果提取关键词，用 BM25 搜索相关模板。
        纯本地操作，无 API 调用，无额外成本。
        """
        if self._retriever is None:
            return "（无历史模板）"

        # 构建查询关键词
        keywords: list[str] = []
        for sa in static_results.values():
            keywords.extend(sa.crypto_imports[:5])
            keywords.extend(sa.env_access[:3])
            for c in sa.token_candidates[:3]:
                keywords.append(c.token_type)
                if c.request_field:
                    keywords.append(c.request_field)

        if not keywords:
            return "（无关键词）"

        query = " ".join(dict.fromkeys(keywords))  # 去重
        templates = self._retriever.bm25_search_templates(query)

        if not templates:
            return "（无匹配模板）"

        lines = [f"BM25 命中 {len(templates)} 个相似模板:"]
        for t in templates:
            lines.append(f"  - {t.name}: {t.description} (算法: {t.algorithm_type})")
            if t.input_fields:
                lines.append(f"    输入: {t.input_fields}")

        return "\n".join(lines)
