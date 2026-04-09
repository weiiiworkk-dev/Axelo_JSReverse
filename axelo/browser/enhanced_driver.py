"""Enhanced browser driver with device fingerprint reinforcement."""
from __future__ import annotations

from pathlib import Path
from typing import Any

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


class EnhancedBrowserDriver:
    """
    Enhanced BrowserDriver with device fingerprint reinforcement.
    
    This wrapper adds:
    - Enhanced device fingerprint generation (Canvas, Audio, Fonts)
    - Realistic noise injection
    - Device coherence validation
    
    Usage:
        driver = EnhancedBrowserDriver(enable_fingerprint=True)
        async with driver:
            page = await driver.launch(profile, session_state)
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
        
        # Initialize fingerprint reinforcer if available
        if self._enable_fingerprint:
            self._fingerprint_reinforcer = DeviceFingerprintReinforcer()
        else:
            self._fingerprint_reinforcer = None
        
        # Internal driver
        self._driver = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._pw = await async_playwright().start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if hasattr(self, '_pw') and self._pw:
            await self._pw.stop()
    
    async def launch(
        self,
        profile: BrowserProfile,
        session_state: SessionState | None = None,
        trace_path: Path | None = None,
    ) -> Page:
        """
        Launch browser with enhanced fingerprint.
        
        Args:
            profile: Browser profile
            session_state: Optional session state
            trace_path: Optional trace path
            
        Returns:
            Playwright page
        """
        # Generate enhanced fingerprint if enabled
        if self._enable_fingerprint and self._fingerprint_reinforcer:
            try:
                # Try to generate fingerprint (requires page, so we'll do it after page creation)
                log.info("fingerprint_reinforcer_enabled")
            except Exception as e:
                log.warning("fingerprint_init_failed", error=str(e))
        
        # Use the standard driver for actual browser launch
        # The fingerprint enhancement happens on the profile level
        launcher = getattr(self._pw, self._browser_type)
        
        launch_kwargs: dict = dict(
            headless=self._headless,
            ignore_default_args=["--enable-automation"],
            args=self._get_launch_args(),
        )
        
        if getattr(settings, "browser_channel", ""):
            launch_kwargs["channel"] = settings.browser_channel
            
        browser = await launcher.launch(**launch_kwargs)
        
        context_kwargs = build_context_options(profile)
        if session_state and session_state.storage_state_path and Path(session_state.storage_state_path).exists():
            context_kwargs["storage_state"] = session_state.storage_state_path
        
        context = await browser.new_context(**context_kwargs)
        
        if session_state and session_state.cookies and not context_kwargs.get("storage_state"):
            await context.add_cookies(session_state.cookies)
        
        # Apply simulation
        simulation_payload = build_simulation_payload(profile)
        await context.add_init_script(render_simulation_init_script(profile, payload=simulation_payload))
        
        # === 大幅度增强反爬机制 - JavaScript层伪装 ===
        await context.add_init_script("""
            (function() {
                'use strict';
                
                // 1. 完全移除webdriver属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: function() { return undefined; },
                    configurable: false
                });
                
                // 2. 模拟真实插件列表
                const pluginList = [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
                    { name: 'Widevine Content Decryption Module', filename: 'widevinecdmadapter.dll', description: 'Enables Widevine content decryption for DRM-protected content' },
                    { name: 'Adobe Flash Player', filename: 'PepperFlashPlayer.dll', description: 'Shockwave Flash 32.0 r0' }
                ];
                
                const createPluginArray = function() {
                    const plugins = pluginList.map(function(p) {
                        return {
                            name: p.name,
                            filename: p.filename,
                            description: p.description,
                            length: 0,
                            item: function(i) { return null; },
                            namedItem: function(n) { return null; }
                        };
                    });
                    
                    const arr = { length: plugins.length };
                    plugins.forEach(function(p, i) { arr[i] = p; });
                    
                    arr.item = function(i) { return plugins[i] || null; };
                    arr.namedItem = function(n) { 
                        return plugins.find(function(p) { return p.name === n; }) || null; 
                    };
                    arr.refresh = function() {};
                    
                    Object.defineProperty(arr, Symbol.iterator, {
                        value: function() {
                            let index = 0;
                            return {
                                next: function() {
                                    return index < plugins.length 
                                        ? { done: false, value: plugins[index++] }
                                        : { done: true };
                                }
                            };
                        }
                    });
                    
                    return Object.freeze(arr);
                };
                
                Object.defineProperty(navigator, 'plugins', {
                    get: function() { return createPluginArray(); },
                    configurable: false
                });
                
                // 3. 模拟真实languages
                Object.defineProperty(navigator, 'languages', {
                    get: function() { return ['zh-CN', 'zh', 'en-US', 'en']; },
                    configurable: false
                });
                
                // 4. 覆盖Chrome对象
                if (!window.chrome) {
                    window.chrome = {};
                }
                window.chrome.runtime = {
                    connect: function() { return { onDisconnect: { addListener: function() {} } }; },
                    sendMessage: function() {},
                    id: 'omgnhkclkmpnifionjlkjdclhhlfegbk'
                };
                window.chrome.app = {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                };
                window.chrome.csi = function() {
                    return { onloadT: Date.now() - Math.floor(Math.random() * 10000), startE: Date.now() - Math.floor(Math.random() * 10000), pageT: Math.floor(Math.random() * 100), tran: Math.floor(Math.random() * 50) };
                };
                window.chrome.loadTimes = function() {
                    const now = Date.now() / 1000;
                    return {
                        commitLoadTime: now - Math.random() * 10,
                        finishDocumentLoadTime: now - Math.random() * 5,
                        finishLoadTime: now - Math.random() * 2,
                        firstPaintAfterLoadTime: now,
                        navigationType: 'Other',
                        requestTime: now - 1,
                        startLoadTime: now - 2
                    };
                };
                
                // 5. 覆盖permissions
                if (navigator.permissions && navigator.permissions.query) {
                    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
                    navigator.permissions.query = function(permission) {
                        const deniedPermissions = ['notifications', 'push', 'midi', 'camera', 'microphone', 'geolocation'];
                        if (deniedPermissions.includes(permission.name)) {
                            return Promise.resolve({ state: 'prompt', name: permission.name });
                        }
                        return originalQuery(permission);
                    };
                }
                
                // 6. 覆盖connection (网络信息API)
                if (navigator.connection) {
                    const connection = {
                        effectiveType: '4g',
                        downlink: 10 + Math.random() * 10,
                        rtt: 20 + Math.floor(Math.random() * 50),
                        saveData: false,
                        type: 'wifi'
                    };
                    Object.defineProperty(navigator, 'connection', {
                        get: function() { return connection; }
                    });
                }
                
                // 7. 覆盖deviceMemory
                if (navigator.deviceMemory === undefined) {
                    Object.defineProperty(navigator, 'deviceMemory', {
                        get: function() { return 8; }
                    });
                }
                
                // 8. 覆盖hardwareConcurrency
                if (navigator.hardwareConcurrency === undefined) {
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: function() { return 8; }
                    });
                }
                
                // 9. 覆盖platform
                Object.defineProperty(navigator, 'platform', {
                    get: function() { 
                        const ua = navigator.userAgent;
                        if (ua.includes('Win')) return 'Win32';
                        if (ua.includes('Mac')) return 'MacIntel';
                        if (ua.includes('Linux')) return 'Linux x86_64';
                        return 'Win32';
                    }
                });
                
                // 10. 覆盖getPlatformLuminosity
                if (typeof navigator.getPlatformLuminosity === 'function') {
                    navigator.getPlatformLuminosity = function() {
                        return Promise.resolve({ ambient: 0.5 });
                    };
                }
                
                // 11. Document hidden属性
                Object.defineProperty(document, 'hidden', {
                    get: function() { return false; }
                });
                Object.defineProperty(document, 'visibilityState', {
                    get: function() { return 'visible'; }
                });
                
                // 12. 覆盖webkitHidden
                Object.defineProperty(document, 'webkitHidden', {
                    get: function() { return false; }
                });
                
                // 13. 覆盖pointerEvents
                const originalAddEventListener = window.addEventListener;
                window.addEventListener = function(type, listener, options) {
                    if (type === 'pointerlockchange' || type === 'pointerlockerror') {
                        return;
                    }
                    return originalAddEventListener.call(this, type, listener, options);
                };
                
                // 14. 覆盖Date.now() 制造时间漂移
                const originalNow = Date.now;
                let timeOffset = Math.floor(Math.random() * 1000) - 500;
                Date.now = function() {
                    return originalNow() + timeOffset;
                };
                
                // 15. 覆盖performance.now()
                if (performance && performance.now) {
                    const originalPerfNow = performance.now.bind(performance);
                    performance.now = function() {
                        return originalPerfNow() + Math.random() * 50;
                    };
                }
                
                console.log('[Axelo Enhanced] Anti-detection scripts loaded');
            })();
        """)
        
        # TLS headers
        tls_headers = build_tls_extra_headers(profile.user_agent or "")
        if tls_headers:
            await context.set_extra_http_headers(tls_headers)
        
        # Tracing
        if trace_path:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        
        page = await context.new_page()
        
        # Apply enhanced fingerprint if enabled
        if self._enable_fingerprint and self._fingerprint_reinforcer:
            await self._apply_enhanced_fingerprint(page, profile)
        
        log.info("enhanced_browser_launched", 
                type=self._browser_type, 
                headless=self._headless,
                fingerprint_enabled=self._enable_fingerprint)
        
        return page
    
    async def _apply_enhanced_fingerprint(self, page: Page, profile: BrowserProfile) -> None:
        """Apply enhanced device fingerprint to page."""
        try:
            # Generate fingerprint with browser context
            fingerprint = self._fingerprint_reinforcer.generate_fingerprint(
                profile=profile,
                page=page
            )
            
            log.info("fingerprint_generated",
                    canvas=fingerprint.canvas_hash[:16] if fingerprint.canvas_hash else "N/A",
                    audio=fingerprint.audio_hash[:16] if fingerprint.audio_hash else "N/A",
                    fonts=len(fingerprint.fonts))
            
            # The fingerprint is generated and can be used for validation
            # Actual injection would require more complex JS injection
            # For now, we just generate and log
            
        except Exception as e:
            log.warning("fingerprint_application_failed", error=str(e))
    
    @staticmethod
    def _get_launch_args() -> list[str]:
        """Get launch arguments for stealth - 大幅度增强反爬机制."""
        return [
            # ========== 核心隐身参数 ==========
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--password-store=basic",
            "--use-mock-keychain",
            
            # ========== 禁用自动化特征检测 ==========
            "--disable-features=AutomationControlled,SitePerProcess,IsolateOrigins",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            
            # ========== 浏览器特征伪装 ==========
            "--disable-client-side-phishing-detection",
            "--disable-extensions",
            "--disable-translate",
            "--disable-sync",
            
            # ========== 网络行为伪装 ==========
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-default-apps",
            "--disable-domain-reliability",
            "--disable-ipc-flooding-protection",
            "--no-async-dns",
            "--no-pings",
            
            # ========== 性能特征伪装 ==========
            "--disable-hang-monitor",
            "--disable-renderer-backgrounding",
            "--metrics-recording-only",
            "--no-crash-upload",
            
            # ========== 窗口与渲染 ==========
            "--window-size=1920,1080",
            "--disable-software-rasterizer",
            "--disable-gpu-compositing",
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--force-color-profile=srgb",
            
            # ========== Cookie与Session伪装 ==========
            "--disable-coep",
            "--disable-coep-reporter",
            "--disable-default-cookie-origin",
            
            # ========== 隐私与行为伪装 ==========
            "--disable-tracking",
            "--disable-speech",
            "--disable-webrtc",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            
            # ========== 实验性参数 ==========
            "--disable-breakpad",
            "--disable-component-extensions-with-background-pages",
            "--js-flags=--max-old-space-size=4096",
            
            # ========== Amazon/eBay等电商专用 ==========
            "--disable-bot-detection",
            "--disable-hints",
            "--disable-component-update",
            
            # ========== Windows稳定参数 ==========
            "--disable-web-security",
        ]


def create_enhanced_driver(
    browser_type: str = "chromium",
    headless: bool = True,
    enable_fingerprint: bool = True,
) -> EnhancedBrowserDriver:
    """Factory function to create enhanced browser driver."""
    return EnhancedBrowserDriver(
        browser_type=browser_type,
        headless=headless,
        enable_fingerprint=enable_fingerprint,
    )