from __future__ import annotations
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis, TokenCandidate
from axelo.models.target import RequestCapture

# 上下文窗口预算（字符）
MAX_CONTEXT_CHARS = 60_000

# 各部分优先级预算
BUDGET = {
    "target_request":    8_000,   # 最高优先级：目标请求的完整信息
    "candidates":        18_000,  # 候选函数源码片段
    "dynamic_trace":     10_000,  # 动态 Hook 轨迹
    "crypto_patterns":    4_000,  # 静态加密模式
    "string_constants":   2_500,  # 关键字符串常量
    "env_access":         1_500,  # 环境变量访问
    "overview":          10_000,  # bundle 概述
}


class ContextBuilder:
    """
    将静态/动态分析结果组装为 AI 分析的上下文字符串。
    按优先级填充，超出预算则截断，确保最重要的信息始终在场。
    """

    def build_analysis_context(
        self,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        target_requests: list[RequestCapture],
    ) -> str:
        sections: list[str] = []
        used = 0

        # 1. 目标请求（最高优先级）
        target_sec = self._format_target_requests(target_requests)
        target_sec = _truncate(target_sec, BUDGET["target_request"])
        sections.append(target_sec)
        used += len(target_sec)

        # 2. 静态候选函数源码
        candidates_sec = self._format_candidates(static_results)
        budget = min(BUDGET["candidates"], MAX_CONTEXT_CHARS - used - 20_000)
        candidates_sec = _truncate(candidates_sec, budget)
        sections.append(candidates_sec)
        used += len(candidates_sec)

        # 3. 动态 Hook 轨迹
        if dynamic and used < MAX_CONTEXT_CHARS - 5_000:
            dyn_sec = self._format_dynamic(dynamic)
            dyn_sec = _truncate(dyn_sec, BUDGET["dynamic_trace"])
            sections.append(dyn_sec)
            used += len(dyn_sec)

        # 4. 加密模式 + 字符串常量
        if used < MAX_CONTEXT_CHARS - 5_000:
            extra = self._format_extra(static_results)
            extra = _truncate(extra, BUDGET["crypto_patterns"] + BUDGET["string_constants"])
            sections.append(extra)

        return "\n\n".join(s for s in sections if s.strip())

    # ── 格式化方法 ───────────────────────────────────────────────

    def _format_target_requests(self, requests: list[RequestCapture]) -> str:
        if not requests:
            return "## 目标请求\n（无）"
        lines = ["## 目标请求（需要逆向复现的请求）"]
        for i, req in enumerate(requests[:3], 1):
            lines.append(f"\n### 请求 {i}")
            lines.append(f"**{req.method}** `{req.url}`")
            if req.request_headers:
                hdrs = "\n".join(f"  {k}: {v}" for k, v in list(req.request_headers.items())[:20])
                lines.append(f"**请求头:**\n{hdrs}")
            if req.request_body:
                body_str = req.request_body.decode("utf-8", errors="replace")[:1000]
                lines.append(f"**请求体:**\n```\n{body_str}\n```")
            lines.append(f"**响应状态:** {req.response_status}")
        return "\n".join(lines)

    def _format_candidates(self, static_results: dict[str, StaticAnalysis]) -> str:
        lines = ["## 静态分析：Token 候选函数"]
        total = 0
        for bundle_id, sa in static_results.items():
            if not sa.token_candidates:
                continue
            lines.append(f"\n### Bundle: {bundle_id}")
            for c in sa.token_candidates[:10]:
                lines.append(f"\n**函数**: `{c.func_id}` | 类型: {c.token_type} | 置信度: {c.confidence:.0%}")
                if c.request_field:
                    lines.append(f"对应字段: `{c.request_field}`")
                lines.append(f"证据: {'; '.join(c.evidence)}")
                if c.source_snippet:
                    snippet = c.source_snippet[:800]
                    lines.append(f"```javascript\n{snippet}\n```")
                total += 1
                if total >= 15:
                    break
            if total >= 15:
                break
        return "\n".join(lines) if total > 0 else "## 静态分析\n（未发现候选函数）"

    def _format_dynamic(self, dynamic: DynamicAnalysis) -> str:
        lines = ["## 动态分析：Hook 拦截轨迹"]
        if dynamic.crypto_primitives:
            lines.append(f"**实际使用的加密原语**: {', '.join(dynamic.crypto_primitives)}")
        if dynamic.confirmed_generators:
            lines.append(f"**推断的生成函数调用栈**: {', '.join(dynamic.confirmed_generators[:5])}")
        if dynamic.field_mapping:
            lines.append("**API → 请求字段映射:**")
            for api, field in dynamic.field_mapping.items():
                lines.append(f"  - `{api}` → `{field}`")

        # 展示关键 Hook 记录（最多10条）
        if dynamic.hook_intercepts:
            lines.append("\n**关键 Hook 调用（按时序）:**")
            for ic in sorted(dynamic.hook_intercepts, key=lambda x: x.sequence)[:10]:
                args_preview = ic.args_repr[:200] if ic.args_repr else ""
                ret_preview = ic.return_repr[:100] if ic.return_repr else ""
                lines.append(
                    f"  [{ic.sequence}] `{ic.api_name}`\n"
                    f"       args: {args_preview}\n"
                    f"       ret:  {ret_preview}"
                )
        return "\n".join(lines)

    def _format_extra(self, static_results: dict[str, StaticAnalysis]) -> str:
        lines = []
        all_crypto: list[str] = []
        all_strings: list[str] = []
        all_env: list[str] = []

        for sa in static_results.values():
            all_crypto.extend(sa.crypto_imports)
            all_strings.extend(sa.string_constants)
            all_env.extend(sa.env_access)

        if all_crypto:
            lines.append("## 加密 API 使用\n" + "\n".join(f"- `{c}`" for c in list(dict.fromkeys(all_crypto))[:20]))
        if all_strings:
            lines.append("## 关键字符串常量\n" + "\n".join(f"- `{s}`" for s in all_strings[:30]))
        if all_env:
            lines.append("## 浏览器环境访问\n" + "\n".join(f"- `{e}`" for e in list(dict.fromkeys(all_env))[:15]))

        return "\n\n".join(lines)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[内容已截断]"
