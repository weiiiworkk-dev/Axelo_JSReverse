"""
playwright_web/conftest.py — 仅提供 Playwright 浏览器 fixtures。

web_server fixture 已统一由 tests/conftest.py（顶层）管理，
本文件不再重复定义，避免双重启动服务导致端口冲突。

browser / context / page fixtures 通过依赖链自动使用顶层的 web_server。
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

from tests.playwright_web.constants import TEST_PORT, BASE_URL  # noqa: F401  (re-exported)


@pytest.fixture(scope="session")
def playwright_sync(web_server) -> Playwright:
    """Session-scoped 同步 Playwright 实例（依赖顶层 web_server fixture）。"""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_sync: Playwright) -> Browser:
    """Session-scoped 浏览器实例。"""
    headless = os.environ.get("AXELO_HEADLESS", "false").lower() == "true"
    br = playwright_sync.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    yield br
    br.close()


@pytest.fixture(scope="function")
def context(browser: Browser) -> BrowserContext:
    """Function-scoped browser context，每个测试独立。"""
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    yield ctx
    ctx.close()


@pytest.fixture(scope="function")
def page(context: BrowserContext) -> Page:
    p = context.new_page()
    yield p
    p.close()
