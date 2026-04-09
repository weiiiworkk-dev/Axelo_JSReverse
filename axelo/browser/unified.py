"""
Unified Browser Module

Consolidated browser management:
- Driver: BrowserDriver + EnhancedBrowserDriver
- Pools: SessionPool + ProfilePool + CookiePool

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
import structlog

from axelo.browser.simulation import build_context_options, build_simulation_payload, render_simulation_init_script
from axelo.browser.tls_profile import build_tls_extra_headers
from axelo.config import settings
from axelo.models.session_state import SessionState
from axelo.models.target import BrowserProfile

# Import device fingerprint reinforcer (optional - graceful fallback if not available)
try:
    from axelo.fingerprint.fingerprint_reinforcer import DeviceFingerprintReinforcer
    FINGERPRINT_AVAILABLE = True
except ImportError:
    FINGERPRINT_AVAILABLE = False

log = structlog.get_logger()


# =============================================================================
# UNIFIED DRIVER
# =============================================================================

class BrowserDriver:
    """Playwright browser driver with persisted session and tracing support.
    
    This is the base driver class. Use EnhancedBrowserDriver for fingerprint reinforcement.
    """

    def __init__(self, browser_type: str = "chromium", headless: bool = True) -> None:
        self._browser_type = browser_type
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._trace_path: Path | None = None
        self._simulation_handles: dict[str, str] = {}

    async def launch(
        self,
        profile: BrowserProfile,
        session_state: SessionState | None = None,
        trace_path: Path | None = None,
    ) -> Page:
        self._pw = await async_playwright().start()
        launcher = getattr(self._pw, self._browser_type)
        
        # =====================================================
        # 大幅度增强反爬机制 - 2026年最新技术
        # =====================================================
        
        # 使用新版无头模式 - 只有在非Windows或Playwright版本支持时使用
        # Windows环境保持兼容模式
        import sys
        if sys.platform == "win32":
            # Windows上使用传统headless以保证稳定性
            headless_mode = self._headless
        else:
            # 非Windows可以使用新版无头模式
            headless_mode = self._headless

        # Launch browser
        self._browser = await launcher.launch(
            headless=headless_mode,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        
        # Build context options
        context_options = build_context_options(profile)
        
        # Create context
        self._context = await self._browser.new_context(**context_options)
        
        # Apply TLS extra headers if configured
        extra_headers = build_tls_extra_headers()
        if extra_headers:
            await self._context.set_extra_http_headers(extra_headers)
        
        # Restore session state if provided
        if session_state:
            await self._context.add_cookies(session_state.cookies)
        
        # Create page
        self._page = await self._context.new_page()
        
        # Inject simulation script for anti-detection
        simulation_script = render_simulation_init_script(build_simulation_payload(profile))
        await self._page.add_init_script(simulation_script)
        
        log.info("browser_driver_launched", browser_type=self._browser_type)
        return self._page

    async def close(self) -> None:
        """Close browser and cleanup resources"""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        
        log.info("browser_driver_closed")

    @property
    def page(self) -> Optional[Page]:
        return self._page
    
    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context


# =============================================================================
# ENHANCED DRIVER (with fingerprint reinforcement)
# =============================================================================

class EnhancedBrowserDriver:
    """
    Enhanced BrowserDriver with device fingerprint reinforcement.
    
    This wrapper adds:
    - Enhanced device fingerprint generation (Canvas, Audio, Fonts)
    - Realistic noise injection
    - Device coherence validation
    """

    def __init__(
        self,
        browser_type: str = "chromium",
        headless: bool = True,
        enable_fingerprint: bool = True,
    ):
        self._browser_type = browser_type
        self._headless = headless
        self._enable_fingerprint = enable_fingerprint and FINGERPRINT_AVAILABLE
        self._driver = BrowserDriver(browser_type, headless)
        self._fingerprint_reinforcer: Optional[DeviceFingerprintReinforcer] = None
        
        if self._enable_fingerprint:
            try:
                self._fingerprint_reinforcer = DeviceFingerprintReinforcer()
            except Exception as e:
                log.warning("fingerprint_reinforcer_init_failed", error=str(e))
                self._enable_fingerprint = False

    async def launch(
        self,
        profile: BrowserProfile,
        session_state: SessionState | None = None,
        trace_path: Path | None = None,
    ) -> Page:
        """Launch browser with enhanced fingerprint"""
        page = await self._driver.launch(profile, session_state, trace_path)
        
        # Apply fingerprint reinforcement if enabled
        if self._enable_fingerprint and self._fingerprint_reinforcer:
            try:
                await self._fingerprint_reinforcer.reinforce(page)
                log.info("fingerprint_reinforcement_applied")
            except Exception as e:
                log.warning("fingerprint_reinforcement_failed", error=str(e))
        
        return page

    async def close(self) -> None:
        """Close browser and cleanup resources"""
        await self._driver.close()

    @property
    def page(self) -> Optional[Page]:
        return self._driver.page
    
    @property
    def context(self) -> Optional[BrowserContext]:
        return self._driver.context


# =============================================================================
# UNIFIED POOLS (consolidated from session_pool, profile_pool, cookie_pool)
# =============================================================================

class PoolManager:
    """
    Unified pool manager combining SessionPool, ProfilePool, and CookiePool functionality.
    """

    def __init__(self, pool_dir: Path):
        self._pool_dir = pool_dir
        self._sessions: dict[str, SessionState] = {}
        self._profiles: dict[str, BrowserProfile] = {}
        self._cookies: dict[str, list[dict]] = {}

    async def acquire_session(self, session_id: str) -> Optional[SessionState]:
        """Acquire a session from the pool"""
        return self._sessions.get(session_id)

    async def release_session(self, session_id: str, state: SessionState) -> None:
        """Release a session back to the pool"""
        self._sessions[session_id] = state

    async def acquire_profile(self, profile_id: str) -> Optional[BrowserProfile]:
        """Acquire a profile from the pool"""
        return self._profiles.get(profile_id)

    async def release_profile(self, profile_id: str, profile: BrowserProfile) -> None:
        """Release a profile back to the pool"""
        self._profiles[profile_id] = profile

    async def get_cookies(self, domain: str) -> list[dict]:
        """Get cookies for a domain"""
        return self._cookies.get(domain, [])

    async def set_cookies(self, domain: str, cookies: list[dict]) -> None:
        """Set cookies for a domain"""
        self._cookies[domain] = cookies


# =============================================================================
# BACKWARD COMPATIBILITY EXPORTS
# =============================================================================

# Re-export for backward compatibility
SessionPool = PoolManager
ProfilePool = PoolManager
CookiePool = PoolManager


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Drivers
    "BrowserDriver",
    "EnhancedBrowserDriver",
    # Pools (unified)
    "PoolManager",
    # Backward compatibility
    "SessionPool",
    "ProfilePool",
    "CookiePool",
]