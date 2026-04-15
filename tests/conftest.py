"""
顶层 conftest.py — 提供 axelo web 服务器生命周期 fixture，
供所有测试（包括 tests/test_suite.py）共享。

端口由 tests/shared_port.py 统一管理，避免与子目录 conftest 冲突。
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

from tests.shared_port import TEST_PORT, BASE_URL  # noqa: F401  (re-exported for test_suite.py)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def web_server():
    """启动 axelo web 服务器进程，测试结束后自动终止。"""
    env = os.environ.copy()
    env["AXELO_HEADLESS"] = "true"
    env["AXELO_BROWSER_CHANNEL"] = ""
    env["AXELO_LOG_LEVEL"] = "warning"
    env.pop("PYTEST_CURRENT_TEST", None)

    cmd = [sys.executable, "-m", "axelo.cli", "web", "--port", str(TEST_PORT), "--no-open"]

    extra_flags: dict = {}
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

    deadline = time.time() + 90
    ready = False
    while time.time() < deadline:
        time.sleep(1)
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            pytest.fail(
                f"axelo web 进程意外退出（code={proc.returncode}，port={TEST_PORT}）:\n{out}"
            )
        try:
            r = httpx.get(f"http://localhost:{TEST_PORT}/", timeout=3)
            if r.status_code < 500:
                ready = True
                break
        except Exception:
            pass

    if not ready:
        proc.terminate()
        pytest.fail(f"axelo web 服务在 90 秒内未就绪（port={TEST_PORT}）")

    yield proc

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def playwright_instance(web_server) -> Playwright:
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Browser:
    headless = os.environ.get("AXELO_HEADLESS", "false").lower() == "true"
    br = playwright_instance.chromium.launch(
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
