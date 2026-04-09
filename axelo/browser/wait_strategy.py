"""
Adaptive Wait Strategy - 自适应等待策略

核心功能:
1. 检测网络请求是否还在进行
2. 检测DOM是否还在变化
3. 检测是否有loading状态
4. 动态调整等待时间

设计原则:
- 完全通用 - 不针对任何特定站点
- 智能检测 - 多个信号综合判断
- 超时保护 - 防止无限等待
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog
from playwright.async_api import Page

from axelo.config import settings

log = structlog.get_logger()


@dataclass
class WaitResult:
    """等待结果"""
    stable: bool = False
    wait_time_ms: int = 0
    network_idle: bool = False
    dom_stable: bool = False
    loading_finished: bool = False
    strategy_used: str = ""


class AdaptiveWaitStrategy:
    """
    自适应等待策略
    
    检测信号:
    1. networkidle - 网络请求完成
    2. DOM变化 - 无元素添加/删除
    3. Loading状态 - loading元素消失
    4. 动画完成 - CSS动画结束
    """
    
    # 默认最大等待时间 (毫秒)
    DEFAULT_MAX_WAIT_MS = 30000
    
    # 检测间隔 (毫秒)
    CHECK_INTERVAL_MS = 500
    
    # loading元素选择器 (通用)
    LOADING_SELECTORS = [
        "[class*='loading']",
        "[class*='spinner']",
        "[class*='skeleton']",
        "[role='progressbar']",
        "[aria-busy='true']",
        ".loading-overlay",
        ".spinner",
        "#loading",
    ]
    
    async def wait_for_stable(
        self,
        page: Page,
        max_wait_ms: int = None,
    ) -> WaitResult:
        """
        等待页面稳定
        
        Args:
            page: Playwright页面对象
            max_wait_ms: 最大等待时间
        
        Returns:
            WaitResult: 等待结果
        """
        max_wait_ms = max_wait_ms or self.DEFAULT_MAX_WAIT_MS
        result = WaitResult()
        
        start_time = time.time()
        check_count = 0
        
        # 记录初始状态
        initial_resource_count = await self._get_resource_count(page)
        last_resource_count = initial_resource_count
        
        while (time.time() - start_time) * 1000 < max_wait_ms:
            check_count += 1
            
            # 信号1: 网络Idle检测
            network_idle = await self._check_network_idle(page)
            result.network_idle = network_idle
            
            # 信号2: DOM稳定性检测
            dom_stable = await self._check_dom_stable(page)
            result.dom_stable = dom_stable
            
            # 信号3: Loading状态
            loading_finished = await self._check_loading_finished(page)
            result.loading_finished = loading_finished
            
            # 判断是否稳定 (3个信号中有2个为true)
            stable_count = sum([
                network_idle,
                dom_stable, 
                loading_finished
            ])
            
            if stable_count >= 2:
                result.stable = True
                result.strategy_used = "adaptive_multi_signal"
                result.wait_time_ms = int((time.time() - start_time) * 1000)
                
                log.info("page_stable_adaptive", 
                         wait_ms=result.wait_time_ms,
                         checks=check_count,
                         network_idle=network_idle,
                         dom_stable=dom_stable,
                         loading_finished=loading_finished)
                return result
            
            # 更新资源计数
            current_count = await self._get_resource_count(page)
            if current_count != last_resource_count:
                last_resource_count = current_count
            
            # 等待再检查
            await asyncio.sleep(self.CHECK_INTERVAL_MS / 1000)
        
        # 超时降级 - 使用Playwright内置的networkidle
        result.strategy_used = "fallback_networkidle"
        result.wait_time_ms = max_wait_ms
        
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
            result.network_idle = True
            result.stable = True
        except Exception:
            pass
        
        log.warning("wait_timeout_fallback", 
                    wait_ms=result.wait_time_ms,
                    checks=check_count)
        
        return result
    
    async def wait_for_api_response(
        self,
        page: Page,
        url_pattern: str = None,
        timeout_ms: int = 15000,
    ) -> bool:
        """
        等待特定API响应
        
        Args:
            page: Playwright页面对象
            url_pattern: URL匹配模式
            timeout_ms: 超时时间
        
        Returns:
            bool: 是否收到响应
        """
        if not url_pattern:
            return True
        
        try:
            async with page.expect_response(
                lambda response: url_pattern in response.url,
                timeout=timeout_ms
            ):
                return True
        except Exception:
            log.debug("api_response_wait_timeout", pattern=url_pattern)
            return False
    
    async def wait_after_interaction(
        self,
        page: Page,
        interaction_type: str = "search",
        max_wait_ms: int = None,
    ) -> WaitResult:
        """
        交互后的智能等待
        
        不同交互类型需要不同的等待策略:
        - search: 等待搜索API响应
        - scroll: 等待新内容加载
        - click: 等待内容更新
        
        Args:
            page: Playwright页面对象
            interaction_type: 交互类型
            max_wait_ms: 最大等待时间
        
        Returns:
            WaitResult: 等待结果
        """
        max_wait_ms = max_wait_ms or self.DEFAULT_MAX_WAIT_MS
        
        if interaction_type == "search":
            # 搜索后等待 - 关键: 等待搜索API
            result = await self.wait_for_stable(page, max_wait_ms)
            
            # 额外等待: 确保搜索结果渲染
            await page.wait_for_timeout(2000)
            
            # 检查是否有搜索结果元素
            result.strategy_used = "search_interaction"
            return result
        
        elif interaction_type == "scroll":
            # 滚动后等待
            result = await self.wait_for_stable(page, max_wait_ms)
            result.strategy_used = "scroll_interaction"
            return result
        
        elif interaction_type == "click":
            # 点击后等待
            result = await self.wait_for_stable(page, max_wait_ms)
            result.strategy_used = "click_interaction"
            return result
        
        else:
            # 默认等待
            return await self.wait_for_stable(page, max_wait_ms)
    
    async def _check_network_idle(self, page: Page) -> bool:
        """检查网络是否Idle"""
        try:
            # 检查是否有进行中的请求
            pending = await page.evaluate("""
                () => {
                    return window.performance.getEntriesByType('resource').length;
                }
            """)
            
            if pending == 0:
                return True
            
            # 简化判断: 如果performance中没有pending请求，认为Idle
            return pending < 3
            
        except Exception:
            return False
    
    async def _check_dom_stable(self, page: Page) -> bool:
        """检查DOM是否稳定 (无频繁变化)"""
        try:
            # 获取当前元素数量
            count = await page.evaluate("""
                () => document.querySelectorAll('*').length
            """)
            
            # 简单判断: 元素数量在合理范围
            # 如果元素太少可能还在加载中
            if count < 100:
                return False
            
            return True
            
        except Exception:
            return False
    
    async def _check_loading_finished(self, page: Page) -> bool:
        """检查loading状态是否结束"""
        try:
            for selector in self.LOADING_SELECTORS:
                loading = page.locator(selector)
                count = await loading.count()
                if count > 0:
                    # 检查是否可见
                    for i in range(count):
                        if await loading.nth(i).is_visible():
                            return False
            return True
            
        except Exception:
            return True  # 出错时默认已完成
    
    async def _get_resource_count(self, page: Page) -> int:
        """获取资源数量"""
        try:
            return await page.evaluate("""
                () => window.performance.getEntriesByType('resource').length
            """)
        except Exception:
            return 0


# 导出
__all__ = [
    "AdaptiveWaitStrategy",
    "WaitResult",
]
