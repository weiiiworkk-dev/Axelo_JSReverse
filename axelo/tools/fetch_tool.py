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
                    required=True,
                ),
                ToolInput(
                    name="urls",
                    type="array",
                    description="要获取的 JS URL 列表",
                    required=True,
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
        base_url = input_data.get("base_url", "")
        urls = input_data.get("urls", [])
        
        if not urls:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: urls",
            )
        
        bundles = []
        failed = []
        
        async with httpx.AsyncClient(timeout=30) as client:
            for url in urls:
                full_url = url if url.startswith("http") else urljoin(base_url, url)
                
                try:
                    response = await client.get(full_url)
                    if response.status_code == 200:
                        bundles.append({
                            "url": full_url,
                            "content": response.text[:500000],  # 500KB 限制
                            "size": len(response.content),
                        })
                except Exception as e:
                    log.warning("fetch_js_failed", url=full_url, error=str(e))
                    failed.append({"url": full_url, "error": str(e)})
        
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output={
                "bundles": bundles,
                "failed": failed,
            },
        )


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(FetchTool())
get_registry().register(JSBundleFetchTool())
