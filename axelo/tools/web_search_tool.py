"""
Web Search Tool - 网络搜索工具

让 AI 可以主动搜索互联网，发现网站信息
"""
from __future__ import annotations

import httpx
import structlog

from axelo.tools.base import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolSchema,
    ToolState,
    ToolResult,
    ToolStatus,
    ToolCategory,
)

log = structlog.get_logger()


class WebSearchTool(BaseTool):
    """网络搜索工具 - 使用 DuckDuckGo API"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "网络搜索：搜索互联网获取网站信息、发现目标URL"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.FETCH,
            input_schema=[
                ToolInput(
                    name="query",
                    type="string",
                    description="搜索关键词",
                    required=True,
                ),
                ToolInput(
                    name="max_results",
                    type="number",
                    description="返回结果数量",
                    required=False,
                    default=5,
                ),
            ],
            output_schema=[
                ToolOutput(name="results", type="array", description="搜索结果列表"),
                ToolOutput(name="query", type="string", description="原始查询"),
                ToolOutput(name="count", type="number", description="结果数量"),
            ],
            timeout_seconds=30,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict, state: ToolState) -> ToolResult:
        """执行网络搜索"""
        query = input_data.get("query")
        max_results = input_data.get("max_results", 5)
        
        if not query:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: query",
            )
        
        try:
            results = await self._search(query, max_results)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "query": query,
                    "results": results,
                    "count": len(results),
                },
            )
            
        except Exception as exc:
            log.error("web_search_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    async def _search(self, query: str, max_results: int) -> list[dict]:
        """执行 DuckDuckGo HTML 搜索"""
        # 使用 DuckDuckGo HTML 搜索（无需 API key）
        url = "https://html.duckduckgo.com/html/"
        
        data = {
            "q": query,
            "b": "",
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        results = []
        
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.post(url, data=data, headers=headers)
            response.raise_for_status()
            
            # 简单解析 HTML 结果
            html = response.text
            
            # 提取结果（简单正则）
            import re
            
            # 匹配结果块
            result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+)</a>'
            
            matches = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)
            
            for i, (url_match, title) in enumerate(matches[:max_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                
                # 清理 HTML 实体
                import html as html_module
                title = html_module.unescape(title)
                snippet = html_module.unescape(snippet)
                
                results.append({
                    "title": title.strip(),
                    "url": url_match,
                    "snippet": snippet.strip() if snippet else "",
                })
        
        return results


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(WebSearchTool())