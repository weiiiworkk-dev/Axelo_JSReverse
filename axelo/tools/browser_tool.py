"""
Browser Tool - 浏览器操作工具

集成 Playwright 进行真实的浏览器操作
支持 stealth 模式 (反检测)
"""
from __future__ import annotations

import asyncio
import json
import time
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
from axelo.tools.stealth_config import (
    get_stealth_args,
    get_context_options,
    get_all_stealth_scripts,
    random_user_agent,
)
from axelo.tools.dynamic_analyzer import DynamicAnalyzer

log = structlog.get_logger()
DEBUG_LOG_PATH = settings.workspace / "debug.log"


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict) -> None:
    payload = {
        "sessionId": "default",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        self._playwright = None
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
                ToolInput(
                    name="stealth",
                    type="boolean",
                    description="启用反检测 stealth 模式 (默认开启)",
                    required=False,
                    default=True,
                ),
                ToolInput(
                    name="dynamic_analysis",
                    type="boolean",
                    description="启用动态JS执行分析 (追踪API调用和签名函数)",
                    required=False,
                    default=False,
                ),
                ToolInput(
                    name="target_functions",
                    type="array",
                    description="要触发的目标函数名列表 (用于动态分析)",
                    required=False,
                    default=[],
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
                ToolOutput(name="dynamic_analysis", type="object", description="动态分析结果 (API调用、签名函数追踪)"),
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
                except Exception as exc:
                    log.warning(
                        "browser_cookies_fetch_failed",
                        error_code="BROWSER_COOKIES_FETCH_FAILED",
                        error=str(exc),
                    )
            
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
            
            # ===== 动态分析 (如果启用) =====
            dynamic_result = {}
            if input_data.get("dynamic_analysis") and self._page:
                try:
                    log.info("dynamic_analysis_start")
                    analyzer = DynamicAnalyzer()
                    target_funcs = input_data.get("target_functions", [])
                    dynamic_result = await analyzer.analyze(self._page, target_funcs)
                    log.info("dynamic_analysis_complete",
                        api_calls=len(dynamic_result.get("api_calls", [])),
                        signatures=len(dynamic_result.get("signature_calls", [])))
                except Exception as e:
                    log.warning("dynamic_analysis_failed", error=str(e))
                    dynamic_result = {"error": str(e)}
            
            # 获取 JS bundles - 从 HTML 和请求中提取
            js_bundles_html = self._extract_js_from_html(html_content)
            js_bundles_req = self._extract_js_from_requests(self._captures)
            
            # 合并并去重
            js_bundles = list(set(js_bundles_html + js_bundles_req))
            
            log.info("js_bundles_extracted", 
                from_html=len(js_bundles_html), 
                from_requests=len(js_bundles_req),
                total=len(js_bundles)
            )
            
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
                "observed_requests": self._captures,  # flat list for downstream compatibility
                "js_bundles": js_bundles,
                "dynamic_analysis": dynamic_result,  # 动态分析结果
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
        
        self._playwright = await async_playwright().start()
        # region agent log
        _debug_log(
            run_id="post-fix",
            hypothesis_id="H9",
            location="axelo/tools/browser_tool.py:_launch_browser",
            message="playwright started",
            data={"started": self._playwright is not None},
        )
        # endregion
        
        # 获取 stealth 配置
        stealth_enabled = input_data.get("stealth", True)  # 默认启用 stealth
        
        # 构建启动参数 (使用 stealth 配置)
        launch_options = {
            "headless": headless,
            "args": get_stealth_args(),  # 使用 stealth args
        }
        
        if user_agent:
            launch_options["args"].append(f"--user-agent={user_agent}")
        elif stealth_enabled:
            # 使用随机 user agent
            launch_options["args"].append(f"--user-agent={random_user_agent()}")
        
        # 启动浏览器
        browser_type = getattr(self._playwright, settings.browser or "chromium")
        
        if proxy:
            launch_options["proxy"] = {"server": proxy}
        
        self._driver = await browser_type.launch(**launch_options)
        
        # 创建 context (使用 stealth 配置)
        if stealth_enabled:
            context_options = get_context_options(randomize=True)
        else:
            context_options = {
                "viewport": {"width": viewport_width, "height": viewport_height},
                "ignore_https_errors": True,
            }
        
        if user_agent:
            context_options["user_agent"] = user_agent
        
        context = await self._driver.new_context(**context_options)
        
        # 注入 stealth 脚本
        if stealth_enabled and self._page:
            stealth_scripts = get_all_stealth_scripts()
            await self._page.evaluateOnNewDocument(stealth_scripts)
        
        # 设置请求拦截
        self._captures = []
        
        async def handle_request(request):
            self._captures.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "timestamp": str(uuid.uuid4()),
            })
        
        context.on("request", handle_request)
        
        # 创建页面并导航
        self._page = await context.new_page()
        
        # 注入 stealth 脚本 (必须在导航前)
        stealth_enabled = input_data.get("stealth", True)
        if stealth_enabled:
            stealth_scripts = get_all_stealth_scripts()
            try:
                await self._page.add_init_script(stealth_scripts)
                log.info("stealth_injected", url=input_data.get("url"))
            except Exception as e:
                log.warning("stealth_inject_failed", error=str(e))
        
        url = input_data.get("url")
        keyword = (input_data.get("keyword") or input_data.get("search_keyword") or "").strip()
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

        # WAF / Bot-challenge 检测与等待
        import asyncio as _asyncio
        try:
            _content_check = await self._page.content()
            _WAF_MARKERS = [
                "awsWafCookieDomainList", "gokuProps",
                "_cf_chl", "challenge-platform", "cf-browser-verification",
                "ddos-guard", "人机验证", "verifying you are human",
            ]
            if any(m in _content_check for m in _WAF_MARKERS) and len(_content_check) < 25000:
                log.info("waf_challenge_detected", url=url, content_length=len(_content_check))
                await _asyncio.sleep(6)
                try:
                    await self._page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
                log.info("waf_wait_complete", url=url)
        except Exception as _waf_err:
            log.warning("waf_check_failed", error=str(_waf_err))

        # 通用搜索交互（无任何站点硬编码）
        if keyword:
            await self._generic_search(self._page, keyword)

        return self._page

    async def _generic_search(self, page, keyword: str) -> None:
        """
        在当前页面寻找搜索框并输入关键词提交。
        完全通用，不依赖任何特定站点逻辑。
        """
        import asyncio as _asyncio
        # 按优先级尝试常见搜索输入选择器
        _search_selectors = [
            "input[type='search']",
            "input[name='q']",
            "input[name='s']",
            "input[name='query']",
            "input[name='keyword']",
            "input[name='search']",
            "input[name='wd']",
            "input[name='text']",
            "input[id*='search' i]",
            "input[class*='search' i]",
            "input[placeholder*='search' i]",
            "input[placeholder*='搜索' i]",
            "[role='searchbox']",
            "input[type='text']",  # 最后兜底
        ]
        for selector in _search_selectors:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    await el.click()
                    await _asyncio.sleep(0.3)
                    await el.fill("")
                    await el.type(keyword, delay=30)
                    await el.press("Enter")
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    log.info("generic_search_performed", selector=selector, keyword=keyword)
                    return
            except Exception:
                continue
        log.warning("generic_search_no_box_found", keyword=keyword)
    
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
        
        # 查找内联 script 中的 src= 或 src =
        pattern3 = r'src\s*=\s*["\']([^"\']+\.js[^"\']*)["\']'
        matches3 = re.findall(pattern3, html, re.IGNORECASE)
        js_files.update(matches3)
        
        # 过滤掉 data: 和 about: 这样的 URL
        filtered = [f for f in js_files if f and not f.startswith(('data:', 'about:', 'blob:'))]
        
        return filtered[:50]  # 限制数量
    
    def _extract_js_from_requests(self, captures: list) -> list[str]:
        """从捕获的请求中提取 JS 文件 URL"""
        js_urls = set()
        
        for req in captures:
            url = req.get("url", "")
            resource_type = req.get("resource_type", "")
            
            # 检查资源类型或 URL 结尾
            if (resource_type == "script" or 
                url.endswith(".js") or 
                "/js/" in url or
                ".js?" in url):  # 包含查询参数的 JS
                js_urls.add(url)
        
        return list(js_urls)[:50]
    
    async def _close_browser(self) -> None:
        """关闭浏览器"""
        try:
            if self._page:
                await self._page.close()
        except Exception as exc:
            log.warning(
                "browser_page_close_failed",
                error_code="BROWSER_PAGE_CLOSE_FAILED",
                error=str(exc),
            )
        
        try:
            if self._driver:
                await self._driver.close()
        except Exception as exc:
            log.warning(
                "browser_driver_close_failed",
                error_code="BROWSER_DRIVER_CLOSE_FAILED",
                error=str(exc),
            )

        try:
            if self._playwright:
                await self._playwright.stop()
                # region agent log
                _debug_log(
                    run_id="post-fix",
                    hypothesis_id="H9",
                    location="axelo/tools/browser_tool.py:_close_browser",
                    message="playwright stopped",
                    data={"stopped": True},
                )
                # endregion
        except Exception as exc:
            log.warning(
                "browser_playwright_stop_failed",
                error_code="BROWSER_PLAYWRIGHT_STOP_FAILED",
                error=str(exc),
            )
            # region agent log
            _debug_log(
                run_id="post-fix",
                hypothesis_id="H9",
                location="axelo/tools/browser_tool.py:_close_browser",
                message="playwright stop failed",
                data={"error": str(exc)},
            )
            # endregion
        
        self._playwright = None
        self._page = None
        self._driver = None
        self._captures = []


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(BrowserTool())