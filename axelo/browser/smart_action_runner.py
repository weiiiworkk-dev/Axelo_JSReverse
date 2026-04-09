"""
Smart Action Runner - 自动交互引擎

核心功能:
1. 自动检测页面交互元素 (搜索框、按钮、分页)
2. 根据intent自动执行交互
3. 多种策略保证触发成功
4. 完全通用 - 不针对任何特定站点

设计原则:
- 稳定性: 多重降级策略
- 健壮性: 异常捕获、超时保护
- 精准度: 基于DOM分析和行为模式
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

import structlog
from playwright.async_api import Page, Locator

from axelo.config import settings
from axelo.models.target import TargetSite
from axelo.policies.runtime import RuntimePolicy

log = structlog.get_logger()


@dataclass
class SearchBoxInfo:
    """搜索框信息"""
    found: bool = False
    selector: str = ""
    input_selector: str = ""
    button_selector: str = ""
    search_type: str = "unknown"  # "search_input", "form", "button_trigger"


@dataclass
class SmartActionResult:
    """智能动作执行结果"""
    success: bool = False
    strategy_used: str = ""
    search_text: str = ""
    executed_actions: int = 0
    errors: list[str] = field(default_factory=list)


class SearchBoxDetector:
    """
    搜索框检测器 - 通用算法
    
    检测策略:
    1. HTML5 search input
    2. 带搜索相关的name/placeholder/aria-label
    3. 搜索表单
    4. 带搜索图标的按钮
    """
    
    # 标准搜索输入框选择器
    SEARCH_INPUT_SELECTORS = [
        "input[type='search']",
        "input[type='text'][name*='search' i]",
        "input[type='text'][name*='q' i]",
        "input[type='text'][name*='keyword' i]",
        "input[type='text'][placeholder*='搜索' i]",
        "input[type='text'][placeholder*='search' i]",
        "input[type='text'][placeholder*='Search' i]",
        "input[type='text'][aria-label*='搜索' i]",
        "input[type='text'][aria-label*='search' i]",
        "input#search",
        "input.search",
        "input[name='search']",
        "input[name='q']",
        "input[name='query']",
        "input[name='keyword']",
        "input[name='search_input']",
    ]
    
    # 搜索表单选择器
    SEARCH_FORM_SELECTORS = [
        "form[action*='search' i]",
        "form[action*='search' i]",
        "form.search-form",
        "form.search-form",
        "form[role='search']",
    ]
    
    # 搜索按钮选择器
    SEARCH_BUTTON_SELECTORS = [
        "button[type='submit']",
        "button:has-text('搜索')",
        "button:has-text('Search')",
        "button:has-text('search')",
        "button.search-btn",
        "button.search-button",
        "[aria-label='搜索']",
        "[aria-label='Search']",
        ".search-submit",
        ".search-button",
    ]
    
    async def detect(self, page: Page) -> SearchBoxInfo:
        """检测页面中的搜索框"""
        
        # 策略1: 直接检测搜索输入框
        for selector in self.SEARCH_INPUT_SELECTORS:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                if count > 0:
                    # 检查是否可见
                    if await locator.first.is_visible():
                        log.debug("search_box_found", selector=selector, type="search_input")
                        return SearchBoxInfo(
                            found=True,
                            selector=selector,
                            input_selector=selector,
                            search_type="search_input"
                        )
            except Exception:
                continue
        
        # 策略2: 检测搜索表单+按钮组合
        for form_selector in self.SEARCH_FORM_SELECTORS:
            try:
                form = page.locator(form_selector)
                if await form.count() > 0:
                    # 查找表单内的输入框
                    input_in_form = form.locator("input[type='text'], input[type='search']")
                    if await input_in_form.count() > 0:
                        input_sel = await input_in_form.first.evaluate("el => el.name || el.id || el.placeholder")
                        button = form.locator("button[type='submit'], button:has-text('搜索')")
                        button_sel = None
                        if await button.count() > 0:
                            button_sel = await button.first.evaluate("el => el.name || el.id || el.textContent")
                        
                        log.debug("search_box_found", selector=form_selector, type="form")
                        return SearchBoxInfo(
                            found=True,
                            selector=form_selector,
                            input_selector=input_sel or f"{form_selector} input",
                            button_selector=button_sel,
                            search_type="form"
                        )
            except Exception:
                continue
        
        # 策略3: 查找搜索按钮反推输入框
        for button_selector in self.SEARCH_BUTTON_SELECTORS:
            try:
                button = page.locator(button_selector)
                if await button.count() > 0 and await button.first.is_visible():
                    # 尝试找相邻的输入框
                    # 先检查按钮前的输入框
                    nearby_input = button.locator("xpath=./preceding-sibling::input")
                    if await nearby_input.count() > 0:
                        input_sel = await nearby_input.first.evaluate("el => el.name || el.id")
                        log.debug("search_box_found", selector=button_selector, type="button_trigger")
                        return SearchBoxInfo(
                            found=True,
                            selector=button_selector,
                            input_selector=input_sel,
                            button_selector=button_selector,
                            search_type="button_trigger"
                        )
            except Exception:
                continue
        
        log.debug("no_search_box_found")
        return SearchBoxInfo(found=False)


class SmartActionRunner:
    """
    智能动作执行器
    
    执行策略 (按优先级):
    1. auto_search - 自动检测并执行搜索
    2. pattern_search - 基于发现的API pattern构造搜索
    3. scroll_trigger - 滚动触发懒加载
    4. fallback_wait - 降级等待
    """
    
    def __init__(self):
        self.search_detector = SearchBoxDetector()
    
    async def run(
        self,
        page: Page,
        target: TargetSite,
        policy: RuntimePolicy,
    ) -> SmartActionResult:
        """执行智能动作"""
        
        result = SmartActionResult()
        
        # 判断是否需要搜索
        resource_kind = (target.intent.resource_kind or "").lower() if target.intent else ""
        needs_search = resource_kind in ("search_results", "product_listing", "content_listing")
        
        if not needs_search:
            # 不需要搜索，执行基础等待
            result.strategy_used = "no_search_needed"
            result.success = True
            return result
        
        # 获取搜索文本
        search_text = self._get_search_text(target)
        
        # 策略1: 自动搜索
        strategy_result = await self._auto_search_strategy(page, target, search_text)
        if strategy_result.success:
            return strategy_result
        
        # 策略2: Pattern搜索 (从已捕获的API推断)
        # 需要从s1_crawl传入已捕获的API，这个在调用时处理
        
        # 策略3: 滚动触发懒加载
        strategy_result = await self._scroll_trigger_strategy(page)
        if strategy_result.success:
            return strategy_result
        
        # 策略4: 降级等待
        result = await self._fallback_strategy(page, target, policy)
        result.errors.append("all_strategies_fallback_to_wait")
        return result
    
    def _get_search_text(self, target: TargetSite) -> str:
        """获取搜索文本"""
        # 优先级: target_hint > interaction_goal > 默认
        if target.target_hint:
            return target.target_hint
        
        if target.interaction_goal:
            # 从goal中提取关键词
            goal = target.interaction_goal.lower()
            # 简单处理: 取第一个有意义的词
            words = goal.replace("/", " ").replace("-", " ").split()
            for word in words:
                if len(word) >= 3 and word not in ("搜索", "search", "商品", "商品", "查找"):
                    return word
        
        return "test"  # 默认测试词
    
    async def _auto_search_strategy(
        self,
        page: Page,
        target: TargetSite,
        search_text: str,
    ) -> SmartActionResult:
        """策略1: 自动搜索"""
        result = SmartActionResult()
        result.strategy_used = "auto_search"
        
        try:
            # 检测搜索框
            search_box = await self.search_detector.detect(page)
            
            if not search_box.found:
                result.errors.append("no_search_box_found")
                return result
            
            # 执行搜索
            if search_box.search_type == "search_input":
                # 直接输入+回车
                await page.fill(search_box.input_selector, search_text)
                await page.press(search_box.input_selector, "Enter")
                result.executed_actions = 2
                
            elif search_box.search_type == "form":
                # 填入输入框，点击按钮
                input_sel = search_box.input_selector
                if input_sel:
                    try:
                        await page.fill(input_sel, search_text)
                    except Exception:
                        await page.locator(input_sel).first.fill(search_text)
                    
                    # 点击搜索按钮
                    if search_box.button_selector:
                        await page.click(search_box.button_selector)
                    else:
                        # 尝试按回车
                        await page.press(input_sel, "Enter")
                    result.executed_actions = 2
                else:
                    result.errors.append("form_input_not_found")
                    return result
                    
            elif search_box.search_type == "button_trigger":
                # 先找输入框，再点击按钮
                # 这个情况比较复杂，简化处理
                try:
                    # 尝试通用的输入方式
                    await page.locator("input[type='text']").first.fill(search_text)
                    await page.click(search_box.selector)
                    result.executed_actions = 2
                except Exception as e:
                    result.errors.append(f"button_trigger_failed: {e}")
                    return result
            
            # 等待一小段时间让搜索请求发出
            await asyncio.sleep(1)
            
            result.success = True
            result.search_text = search_text
            log.info("auto_search_success", text=search_text, type=search_box.search_type)
            
        except Exception as e:
            result.errors.append(f"auto_search_error: {e}")
            log.warning("auto_search_failed", error=str(e))
        
        return result
    
    async def _scroll_trigger_strategy(self, page: Page) -> SmartActionResult:
        """策略3: 滚动触发懒加载"""
        result = SmartActionResult()
        result.strategy_used = "scroll_trigger"
        
        try:
            # 执行多次滚动
            for i in range(3):
                await page.evaluate("""
                    () => {
                        window.scrollBy(0, window.innerHeight * 0.8);
                    }
                """)
                await asyncio.sleep(500)
            
            # 滚动回顶部
            await page.evaluate("() => window.scrollTo(0, 0)")
            
            result.success = True
            result.executed_actions = 4
            log.info("scroll_trigger_success")
            
        except Exception as e:
            result.errors.append(f"scroll_error: {e}")
            log.warning("scroll_trigger_failed", error=str(e))
        
        return result
    
    async def _fallback_strategy(
        self,
        page: Page,
        target: TargetSite,
        policy: RuntimePolicy,
    ) -> SmartActionResult:
        """策略4: 降级等待"""
        result = SmartActionResult()
        result.strategy_used = "fallback_wait"
        
        # 延长等待时间
        wait_time = max(policy.post_navigation_wait_ms, 10000)
        await page.wait_for_timeout(wait_time)
        
        result.success = True
        result.executed_actions = 1
        log.info("fallback_wait_completed", wait_ms=wait_time)
        
        return result


# 导出
__all__ = [
    "SmartActionRunner",
    "SearchBoxDetector", 
    "SearchBoxInfo",
    "SmartActionResult",
]
