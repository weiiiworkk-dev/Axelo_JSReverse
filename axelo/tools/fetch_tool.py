"""
Fetch Tool - 数据获取工具

从 s2_fetch 重写，封装 JS bundle 下载功能
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

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


@dataclass
class FetchOptions:
    """获取选项"""
    timeout: int = 30000
    max_size: int = 1024 * 1024  # 1MB
    follow_redirects: bool = True
    headers: dict = field(default_factory=dict)


@dataclass
class FetchOutput:
    """获取输出"""
    url: str
    content: str = ""
    status_code: int = 0
    headers: dict = field(default_factory=dict)
    content_type: str = ""
    encoding: str = "utf-8"


class FetchTool(BaseTool):
    """数据获取工具"""
    
    def __init__(self):
        super().__init__()
        self._client = None
    
    @property
    def name(self) -> str:
        return "fetch"
    
    @property
    def description(self) -> str:
        return "数据获取：下载 JavaScript bundles、HTML 页面"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.FETCH,
            input_schema=[
                ToolInput(
                    name="url",
                    type="string",
                    description="目标URL",
                    required=True,
                ),
                ToolInput(
                    name="type",
                    type="string",
                    description="获取类型: html, js, json",
                    required=False,
                    default="html",
                ),
                ToolInput(
                    name="timeout",
                    type="number",
                    description="超时时间(毫秒)",
                    required=False,
                    default=30000,
                ),
                ToolInput(
                    name="max_size",
                    type="number",
                    description="最大下载大小(字节)",
                    required=False,
                    default=1048576,
                ),
                ToolInput(
                    name="referer",
                    type="string",
                    description="Referer 头",
                    required=False,
                ),
            ],
            output_schema=[
                ToolOutput(name="url", type="string", description="实际URL"),
                ToolOutput(name="content", type="string", description="内容"),
                ToolOutput(name="status_code", type="number", description="状态码"),
                ToolOutput(name="headers", type="object", description="响应头"),
                ToolOutput(name="content_type", type="string", description="内容类型"),
            ],
            timeout_seconds=60,
            retry_enabled=True,
            max_retries=3,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行获取操作"""
        url = input_data.get("url")
        fetch_type = input_data.get("type", "html")
        
        if not url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: url",
            )
        
        try:
            output = await self._fetch(url, input_data, fetch_type)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "url": output.url,
                    "content": output.content,
                    "status_code": output.status_code,
                    "headers": output.headers,
                    "content_type": output.content_type,
                },
            )
            
        except Exception as exc:
            log.error("fetch_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    async def _fetch(self, url: str, input_data: dict, fetch_type: str) -> FetchOutput:
        """执行 HTTP 请求"""
        timeout = input_data.get("timeout", 30000) / 1000
        max_size = input_data.get("max_size", 1048576)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            **input_data.get("headers", {}),
        }
        
        if input_data.get("referer"):
            headers["Referer"] = input_data["referer"]
        
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            
            output = FetchOutput(
                url=str(response.url),
                status_code=response.status_code,
                headers=dict(response.headers),
                content_type=response.headers.get("content-type", ""),
            )
            
            # 检查内容类型
            if fetch_type == "js" and "javascript" not in output.content_type:
                # 可能需要重试获取 JS
                pass
            
            # 限制大小
            content = response.content[:max_size]
            output.content = content.decode("utf-8", errors="replace")
            
            return output


class JSBundleFetchTool(BaseTool):
    """JS Bundle 批量获取工具"""
    
    @property
    def name(self) -> str:
        return "fetch_js_bundles"
    
    @property
    def description(self) -> str:
        return "批量获取 JavaScript bundles"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.FETCH,
            input_schema=[
                ToolInput(
                    name="base_url",
                    type="string",
                    description="基础URL",
                    required=False,
                ),
                ToolInput(
                    name="urls",
                    type="array",
                    description="要获取的 JS URL 列表",
                    required=True,
                ),
                ToolInput(
                    name="max_concurrency",
                    type="number",
                    description="最大并发下载数",
                    required=False,
                    default=5,
                ),
                ToolInput(
                    name="max_bundle_size",
                    type="number",
                    description="单个 bundle 最大字节数",
                    required=False,
                    default=500000,
                ),
                ToolInput(
                    name="max_total_bytes",
                    type="number",
                    description="总下载字节上限",
                    required=False,
                    default=4000000,
                ),
            ],
            output_schema=[
                ToolOutput(name="bundles", type="array", description="JS bundles"),
                ToolOutput(name="failed", type="array", description="失败的URL"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """批量获取 JS bundles"""
        base_url = input_data.get("base_url") or input_data.get("page_url") or input_data.get("url", "")
        urls = input_data.get("urls") or input_data.get("js_bundles") or []
        
        if not urls:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: urls",
            )
        
        bundles = []
        failed = []
        max_concurrency = int(input_data.get("max_concurrency", 5))
        max_bundle_size = int(input_data.get("max_bundle_size", 500000))
        max_total_bytes = int(input_data.get("max_total_bytes", 4000000))
        lock = asyncio.Lock()
        total_bytes = 0
        sem = asyncio.Semaphore(max(1, min(max_concurrency, 20)))

        async def _fetch_one(raw_url: str, client: httpx.AsyncClient) -> None:
            nonlocal total_bytes
            full_url = raw_url if raw_url.startswith("http") else urljoin(base_url, raw_url)
            try:
                async with sem:
                    response = await client.get(full_url)
                if response.status_code != 200:
                    failed.append({"url": full_url, "error": f"HTTP {response.status_code}"})
                    return
                content_bytes = response.content[:max_bundle_size]
                async with lock:
                    if total_bytes >= max_total_bytes:
                        failed.append({"url": full_url, "error": "total byte cap reached"})
                        return
                    remain = max_total_bytes - total_bytes
                    if len(content_bytes) > remain:
                        content_bytes = content_bytes[:remain]
                    total_bytes += len(content_bytes)
                bundles.append({
                    "url": full_url,
                    "content": content_bytes.decode("utf-8", errors="replace"),
                    "size": len(content_bytes),
                })
            except Exception as exc:
                log.warning("fetch_js_failed", url=full_url, error=str(exc))
                failed.append({"url": full_url, "error": str(exc)})

        async with httpx.AsyncClient(timeout=30) as client:
            await asyncio.gather(*[_fetch_one(url, client) for url in urls])
        
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output={
                "bundles": bundles,
                "failed": failed,
                "total_bytes": total_bytes,
            },
        )


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(FetchTool())
get_registry().register(JSBundleFetchTool())
