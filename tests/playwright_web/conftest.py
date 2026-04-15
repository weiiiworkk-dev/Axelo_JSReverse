"""Playwright Web 测试 conftest — 同步版本。

使用同步 Playwright API，完全规避 pytest-asyncio 的 event loop scope 问题。

职责：
1. 在测试套件启动前，以子进程方式启动 axelo web 服务（动态端口）
2. 等待服务就绪（health check）
3. 提供同步 Playwright browser / page fixture（headful 模式）
4. 测试套件结束后，清理浏览器和服务进程
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

from tests.playwright_web.constants import TEST_PORT, BASE_URL  # noqa: F401  (re-exported)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ──────────────────────────────────────────────────────────────
# Server lifecycle (session-scoped, sync)
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def web_server():
    """启动 axelo web 服务，返回子进程对象；测试结束后终止。"""
    env = os.environ.copy()
    env["AXELO_HEADLESS"] = "true"
    env["AXELO_BROWSER_CHANNEL"] = ""
    env["AXELO_LOG_LEVEL"] = "warning"
    env.pop("PYTEST_CURRENT_TEST", None)

    port = TEST_PORT
    cmd = [sys.executable, "-m", "axelo.cli", "web", "--port", str(port), "--no-open"]

    extra_flags = {}
    if sys.platform == "win32":
        extra_flags["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        cwd=str(_PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **extra_flags,
    )

    # 等待服务就绪（最多 90 秒）
    deadline = time.time() + 90
    ready = False
    while time.time() < deadline:
        time.sleep(1)
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            pytest.fail(
                f"axelo web 进程意外退出（code={proc.returncode}，port={port}）:\n{out}"
            )
        try:
            r = httpx.get(f"http://localhost:{port}/", timeout=3)
            if r.status_code < 500:
                ready = True
                break
        except Exception:
            pass

    if not ready:
        proc.terminate()
        pytest.fail(f"axelo web 服务在 90 秒内未就绪（port={port}）")

    yield proc

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ──────────────────────────────────────────────────────────────
# Playwright — 同步 API（session-scoped）
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def playwright_sync(web_server) -> Playwright:
    """Session-scoped 同步 Playwright 实例。"""
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
