from __future__ import annotations

import secrets
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
import structlog

from axelo.browser.simulation import build_context_options, render_simulation_init_script
from axelo.models.session_state import SessionState
from axelo.models.target import BrowserProfile

log = structlog.get_logger()

# Chromium launch flags that suppress automation-exposure signals.
_STEALTH_ARGS: list[str] = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
]


class BrowserDriver:
    """Playwright browser driver with persisted session and tracing support."""

    def __init__(self, browser_type: str = "chromium", headless: bool = True) -> None:
        self._browser_type = browser_type
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._trace_path: Path | None = None

    async def launch(
        self,
        profile: BrowserProfile,
        session_state: SessionState | None = None,
        trace_path: Path | None = None,
    ) -> Page:
        self._pw = await async_playwright().start()
        launcher = getattr(self._pw, self._browser_type)
        self._browser = await launcher.launch(
            headless=self._headless,
            args=_STEALTH_ARGS,
        )

        # Randomise pointer seed per session so mouse-path statistics differ
        # across runs and cannot be matched to a fixed generator signature.
        session_profile = profile.model_copy(deep=True)
        session_profile.interaction_simulation.pointer.default_seed = (
            secrets.randbelow(2**31 - 1) + 1
        )

        context_kwargs = build_context_options(session_profile)
        if session_state and session_state.storage_state_path and Path(session_state.storage_state_path).exists():
            context_kwargs["storage_state"] = session_state.storage_state_path

        self._context = await self._browser.new_context(**context_kwargs)

        if session_state and session_state.cookies and not context_kwargs.get("storage_state"):
            await self._context.add_cookies(session_state.cookies)

        await self._context.add_init_script(render_simulation_init_script(session_profile))

        self._trace_path = trace_path
        if self._trace_path:
            self._trace_path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)

        self._page = await self._context.new_page()
        log.info("browser_launched", type=self._browser_type, headless=self._headless)
        return self._page

    async def export_storage_state(self) -> dict:
        if self._context is None:
            return {}
        return await self._context.storage_state()

    async def export_cookies(self) -> list[dict]:
        if self._context is None:
            return []
        return await self._context.cookies()

    async def simulation_status(self) -> dict:
        if self._page is None:
            return {}
        return await self._page.evaluate(
            """(() => ({
                environment: window.__sim_env__ && typeof window.__sim_env__.getStatus === 'function'
                  ? window.__sim_env__.getStatus()
                  : null,
                interaction: window.__sim_ia__ && typeof window.__sim_ia__.getStatus === 'function'
                  ? window.__sim_ia__.getStatus()
                  : null,
            }))()"""
        )

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("BrowserDriver has not been launched")
        return self._context

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserDriver has not been launched")
        return self._page

    async def close(self) -> None:
        if self._context and self._trace_path:
            await self._context.tracing.stop(path=str(self._trace_path))
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.info("browser_closed")

    async def __aenter__(self) -> "BrowserDriver":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
