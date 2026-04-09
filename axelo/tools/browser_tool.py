"""
Browser Tool - 浏览器操作工具

集成 Playwright 进行真实的浏览器操作
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
from axelo.config import settings

log = structlog.get_logger()


@dataclass
class BrowserOptions:
    """浏览器选项"""
    headless: bool = True
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str | None = None
    proxy: str | None = None
    timeout: int = 30000
    enable_stealth: bool = True


@dataclass
class BrowserOutput:
    """浏览器输出"""
    session_id: str = ""
    page_url: str = ""
    cookies: list[dict] = field(default_factory=list)
    local_storage: dict = field(default_factory=dict)
    session_storage: dict = field(default_factory=dict)
    captures: dict = field(default_factory=dict)  # 请求/响应捕获
    js_bundles: list[str] = field(default_factory=list)
    page_title: str = ""
    html_content: str = ""


class BrowserTool(BaseTool):
    """浏览器操作工具 - 真实 Playwright 集成"""
    
    def __init__(self):
        super().__init__()
        self._driver = None
        self._page = None
        self._captures: list[dict] = []
    
    @property
    def name(self) -> str:
        return "browser"
    
    @property
    def description(self) -> str:
        return "浏览器操作：抓取页面、获取cookies、执行JavaScript"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.BROWSER,
            input_schema=[
                ToolInput(
                    name="url",
                    type="string",
                    description="目标URL",
                    required=True,
                ),
                ToolInput(
                    name="goal",
                    type="string",
                    description="爬取目标描述",
                    required=True,
                ),
                ToolInput(
                    name="headless",
                    type="boolean",
                    description="是否无头模式",
                    required=False,
                    default=True,
                ),
                ToolInput(
                    name="viewport_width",
                    type="number",
                    description="视口宽度",
                    required=False,
                    default=1920,
                ),
                ToolInput(
                    name="viewport_height",
                    type="number",
                    description="视口高度",
                    required=False,
                    default=1080,
                ),
                ToolInput(
                    name="user_agent",
                    type="string",
                    description="自定义User-Agent",
                    required=False,
                ),
                ToolInput(
                    name="proxy",
                    type="string",
                    description="代理服务器",
                    required=False,
                ),
                ToolInput(
                    name="actions",
                    type="array",
                    description="要执行的动作序列",
                    required=False,
                    default=[],
                ),
                ToolInput(
                    name="wait_for_selector",
                    type="string",
                    description="等待元素选择器",
                    required=False,
                ),
                ToolInput(
                    name="wait_for_timeout",
                    type="number",
                    description="等待超时(毫秒)",
                    required=False,
                    default=5000,
                ),
            ],
            output_schema=[
                ToolOutput(name="session_id", type="string", description="会话ID"),
                ToolOutput(name="page_url", type="string", description="最终页面URL"),
                ToolOutput(name="page_title", type="string", description="页面标题"),
                ToolOutput(name="html_content", type="string", description="页面HTML"),
                ToolOutput(name="cookies", type="array", description="Cookies"),
                ToolOutput(name="local_storage", type="object", description="LocalStorage"),
                ToolOutput(name="session_storage", type="object", description="SessionStorage"),
                ToolOutput(name="captures", type="object", description="请求/响应捕获"),
                ToolOutput(name="js_bundles", type="array", description="JavaScript文件列表"),
            ],
            timeout_seconds=300,
            retry_enabled=True,
            max_retries=3,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行浏览器操作"""
        url = input_data.get("url")
        goal = input_data.get("goal")
        
        if not url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: url",
            )
        
        # 确保 URL 有协议
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        
        try:
            # 初始化浏览器
            page = await self._launch_browser(input_data)
            
            # 执行动作
            if input_data.get("actions"):
                await self._execute_actions(page, input_data["actions"])
            
            # 等待页面稳定
            wait_for = input_data.get("wait_for_selector")
            timeout = input_data.get("wait_for_timeout", 5000)
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=timeout)
                except Exception as e:
                    log.warning("wait_for_selector_failed", selector=wait_for, error=str(e))
            
            # 获取页面数据
            page_url = page.url
            page_title = await page.title() if page else ""
            html_content = await page.content() if page else ""
            
            # 获取 cookies
            cookies = []
            if self._page:
                try:
                    cookies = await self._page.context.cookies()
                except Exception:
                    pass
            
            # 获取 storage
            local_storage = {}
            session_storage = {}
            if self._page:
                try:
                    local_storage = await self._page.evaluate("() => JSON.stringify(localStorage)")
                    local_storage = json.loads(local_storage) if local_storage else {}
                    session_storage = await self._page.evaluate("() => JSON.stringify(sessionStorage)")
                    session_storage = json.loads(session_storage) if session_storage else {}
                except Exception as e:
                    log.warning("storage_fetch_failed", error=str(e))
            
            # 获取 JS bundles
            js_bundles = self._extract_js_from_html(html_content)
            
            # 关闭浏览器
            await self._close_browser()
            
            output = {
                "session_id": session_id,
                "page_url": page_url,
                "page_title": page_title,
                "html_content": html_content[:100000],  # 限制大小
                "cookies": cookies,
                "local_storage": local_storage,
                "session_storage": session_storage,
                "captures": {"requests": self._captures},
                "js_bundles": js_bundles,
            }
            
            log.info("browser_tool_success", session_id=session_id, url=page_url)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=output,
            )
            
        except Exception as exc:
            log.error("browser_tool_failed", error=str(exc), url=url)
            await self._close_browser()
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    async def _launch_browser(self, input_data: dict[str, Any]):
        """启动浏览器并导航到 URL"""
        from playwright.async_api import async_playwright
        
        headless = input_data.get("headless", settings.headless)
        viewport_width = input_data.get("viewport_width", 1920)
        viewport_height = input_data.get("viewport_height", 1080)
        user_agent = input_data.get("user_agent")
        proxy = input_data.get("proxy")
        
        log.info("browser_launch", url=input_data.get("url"), headless=headless)
        
        pw = await async_playwright().start()
        
        # 构建启动参数
        launch_options = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--disable-dev-shm-usage",
            ],
        }
        
        if user_agent:
            launch_options["args"].append(f"--user-agent={user_agent}")
        
        # 启动浏览器
        browser_type = getattr(pw, settings.browser or "chromium")
        
        if proxy:
            launch_options["proxy"] = {"server": proxy}
        
        self._driver = await browser_type.launch(**launch_options)
        
        # 创建 context
        context_options = {
            "viewport": {"width": viewport_width, "height": viewport_height},
            "ignore_https_errors": True,
        }
        
        if user_agent:
            context_options["user_agent"] = user_agent
        
        context = await self._driver.new_context(**context_options)
        
        # 设置请求拦截
        self._captures = []
        
        async def handle_request(request):
            self._captures.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "timestamp": str(uuid.uuid4()),
            })
        
        await context.on("request", handle_request)
        
        # 创建页面并导航
        self._page = await context.new_page()
        
        # 导航到目标 URL
        url = input_data.get("url")
        timeout = input_data.get("timeout", 30000)
        
        try:
            await self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        except Exception as e:
            log.warning("page_navigation_warning", error=str(e))
            # 尝试继续
            try:
                await self._page.goto(url, timeout=timeout, wait_until="load")
            except Exception as e2:
                log.warning("page_navigation_retry_failed", error=str(e2))
        
        return self._page
    
    async def _execute_actions(self, page, actions: list[dict]) -> None:
        """执行动作序列"""
        for action in actions:
            action_type = action.get("type", "")
            
            try:
                if action_type == "click":
                    selector = action.get("selector")
                    if selector:
                        await page.click(selector, timeout=10000)
                        log.debug("browser_action_click", selector=selector)
                        
                elif action_type == "type":
                    selector = action.get("selector")
                    text = action.get("text", "")
                    if selector and text:
                        await page.fill(selector, text)
                        log.debug("browser_action_type", selector=selector, text=text[:20])
                        
                elif action_type == "scroll":
                    x = action.get("x", 0)
                    y = action.get("y", 0)
                    await page.evaluate(f"window.scrollTo({x}, {y})")
                    log.debug("browser_action_scroll", x=x, y=y)
                    
                elif action_type == "wait":
                    duration = action.get("duration", 1000)
                    await page.wait_for_timeout(duration)
                    log.debug("browser_action_wait", duration=duration)
                    
                elif action_type == "goto":
                    url = action.get("url")
                    if url:
                        await page.goto(url, timeout=30000)
                        log.debug("browser_action_goto", url=url)
                        
            except Exception as e:
                log.warning("action_execution_failed", action=action_type, error=str(e))
    
    def _extract_js_from_html(self, html: str) -> list[str]:
        """从 HTML 中提取 JS 文件 URL"""
        import re
        
        js_files = set()
        
        # 查找 <script src="...">
        pattern = r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']'
        matches = re.findall(pattern, html, re.IGNORECASE)
        js_files.update(matches)
        
        # 查找 <script>... src
        pattern2 = r'src=["\']([^"\']+\.js[^"\']*)["\']'
        matches2 = re.findall(pattern2, html, re.IGNORECASE)
        js_files.update(matches2)
        
        return list(js_files)
    
    async def _close_browser(self) -> None:
        """关闭浏览器"""
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        
        try:
            if self._driver:
                await self._driver.close()
        except Exception:
            pass
        
        self._page = None
        self._driver = None
        self._captures = []


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(BrowserTool())