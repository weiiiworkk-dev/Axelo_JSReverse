"""Honeypot detector - Identify hidden traps in web pages."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class HiddenField:
    """Hidden form field that might be a honeypot."""
    tag: str
    name: str
    field_type: str
    value: str
    is_hidden: bool
    is_suspicious: bool


@dataclass
class TrapLink:
    """Link that might be a trap."""
    text: str
    href: str
    is_visible: bool
    is_offscreen: bool
    is_suspicious: bool


@dataclass
class HoneypotReport:
    """Report of honeypot detection results."""
    hidden_fields: list[HiddenField] = field(default_factory=list)
    trap_links: list[TrapLink] = field(default_factory=list)
    decoy_data: list[dict] = field(default_factory=list)
    css_traps: list[dict] = field(default_factory=list)
    risk_score: float = 0.0
    
    @property
    def has_traps(self) -> bool:
        """Check if any traps were found."""
        return len(self.hidden_fields) > 0 or len(self.trap_links) > 0


class HoneypotDetector:
    """Honeypot detector - Identify hidden traps in web pages."""
    
    # Suspicious field name patterns
    HONEYTOP_PATTERNS = [
        "honeypot", "trap", "bot", "spam", "fake", "hidden",
        "secret", "confirm", "anti", "check", "valid",
        "human", "robot", "test", "dummy", "空白",
    ]
    
    # Suspicious link patterns
    TRAP_LINK_PATTERNS = [
        "click", "track", "ad", "promo", "gift", "winner",
        "claim", "free", "offer", "deal", "win", "prize",
    ]
    
    def __init__(self):
        self._suspicious_names = [p.lower() for p in self.HONEYTOP_PATTERNS]
        self._trap_patterns = [p.lower() for p in self.TRAP_LINK_PATTERNS]
    
    async def scan_page(self, page: Any) -> HoneypotReport:
        """Scan page and generate honeypot report.
        
        Args:
            page: Playwright page
            
        Returns:
            HoneypotReport with detected traps
        """
        report = HoneypotReport()
        
        # Run all detections in parallel
        hidden_fields, trap_links, decoy_data, css_traps = await asyncio.gather(
            self._find_hidden_fields(page),
            self._find_trap_links(page),
            self._find_decoy_data(page),
            self._find_css_traps(page),
        )
        
        report.hidden_fields = hidden_fields
        report.trap_links = trap_links
        report.decoy_data = decoy_data
        report.css_traps = css_traps
        report.risk_score = self._calculate_risk(report)
        
        if report.has_traps:
            log.info("honeypot_detected",
                    hidden_fields=len(hidden_fields),
                    trap_links=len(trap_links),
                    risk_score=report.risk_score)
        
        return report
    
    async def _find_hidden_fields(self, page: Any) -> list[HiddenField]:
        """Find hidden form fields that might be honeypots."""
        try:
            fields = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('input, select, textarea').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        
                        // Check if hidden
                        const isHidden = 
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            style.opacity === '0' ||
                            rect.width === 0 ||
                            rect.height === 0 ||
                            parseFloat(style.opacity) < 0.01;
                        
                        // Check for suspicious name
                        const name = (el.name || el.id || '').toLowerCase();
                        const isSuspicious = [
                            'honeypot', 'trap', 'bot', 'spam', 'fake',
                            'hidden', 'secret', 'confirm', 'anti', 'check',
                            'valid', 'human', 'robot', 'test', 'dummy'
                        ].some(p => name.includes(p));
                        
                        if (isHidden || isSuspicious) {
                            results.push({
                                tag: el.tagName.toLowerCase(),
                                name: el.name || el.id || '',
                                type: el.type || 'text',
                                value: el.value || '',
                                hidden: isHidden,
                                suspicious: isSuspicious
                            });
                        }
                    });
                    return results;
                }
            """)
            
            return [HiddenField(
                tag=f["tag"],
                name=f["name"],
                field_type=f["type"],
                value=f["value"],
                is_hidden=f["hidden"],
                is_suspicious=f["suspicious"],
            ) for f in fields]
            
        except Exception as e:
            log.error("find_hidden_fields_failed", error=str(e))
            return []
    
    async def _find_trap_links(self, page: Any) -> list[TrapLink]:
        """Find trap links (invisible or suspicious links)."""
        try:
            links = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('a').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        
                        // Check visibility
                        const isVisible = 
                            style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 && rect.height > 0 &&
                            style.opacity !== '0' &&
                            parseFloat(style.opacity) > 0.01;
                        
                        // Check if offscreen
                        const isOffscreen = 
                            rect.top > window.innerHeight ||
                            rect.left > window.innerWidth ||
                            rect.bottom < 0 ||
                            rect.right < 0;
                        
                        // Check suspicious content
                        const text = (el.textContent || '').toLowerCase();
                        const href = (el.href || '').toLowerCase();
                        
                        const suspiciousPatterns = [
                            'click', 'track', 'ad', 'promo', 'gift',
                            'winner', 'claim', 'free', 'offer', 'deal'
                        ];
                        
                        const isSuspicious = 
                            suspiciousPatterns.some(p => text.includes(p)) ||
                            suspiciousPatterns.some(p => href.includes(p));
                        
                        // Skip navigation links
                        const isNavigation = 
                            text.length > 50 || 
                            href.includes('/menu') ||
                            href.includes('/nav') ||
                            href.includes('/menu');
                        
                        if (!isNavigation && (!isVisible || isOffscreen || isSuspicious)) {
                            results.push({
                                text: el.textContent?.substring(0, 50) || '',
                                href: el.href || '',
                                visible: isVisible,
                                offscreen: isOffscreen,
                                suspicious: isSuspicious
                            });
                        }
                    });
                    return results;
                }
            """)
            
            return [TrapLink(
                text=l["text"],
                href=l["href"],
                is_visible=l["visible"],
                is_offscreen=l["offscreen"],
                is_suspicious=l["suspicious"],
            ) for l in links]
            
        except Exception as e:
            log.error("find_trap_links_failed", error=str(e))
            return []
    
    async def _find_decoy_data(self, page: Any) -> list[dict]:
        """Find decoy data (fake options in dropdowns, etc)."""
        try:
            decoys = await page.evaluate("""
                () => {
                    const results = [];
                    
                    // Check dropdowns for suspicious options
                    document.querySelectorAll('select').forEach(select => {
                        const options = Array.from(select.options);
                        const suspiciousOptions = options.filter(opt => {
                            const text = (opt.text || '').toLowerCase();
                            return text.includes('select') || 
                                   text.includes('choose') ||
                                   text.includes('option') ||
                                   text.includes('please');
                        });
                        
                        if (suspiciousOptions.length > 0 && options.length > 3) {
                            results.push({
                                type: 'select_decoy',
                                selector: select.id || select.name || 'unknown',
                                options_count: options.length,
                                decoy_count: suspiciousOptions.length
                            });
                        }
                    });
                    
                    return results;
                }
            """)
            
            return decoys
            
        except Exception as e:
            log.error("find_decoy_data_failed", error=str(e))
            return []
    
    async def _find_css_traps(self, page: Any) -> list[dict]:
        """Find CSS-based traps (invisible clickable areas)."""
        try:
            traps = await page.evaluate("""
                () => {
                    const results = [];
                    
                    // Find elements that are clickable but not visible
                    document.querySelectorAll('a, button, input[type="submit"]').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        
                        // Check if clickable but not visible
                        const isClickable = 
                            el.tagName.toLowerCase() === 'button' ||
                            el.type === 'submit' ||
                            el.getAttribute('onclick') ||
                            el.getAttribute('href');
                        
                        const isInvisible = 
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            rect.width === 0 ||
                            rect.height === 0 ||
                            parseFloat(style.opacity) < 0.01;
                        
                        if (isClickable && isInvisible) {
                            results.push({
                                type: 'css_trap',
                                tag: el.tagName.toLowerCase(),
                                visible_width: rect.width,
                                visible_height: rect.height,
                                display: style.display,
                                visibility: style.visibility
                            });
                        }
                    });
                    
                    return results;
                }
            """)
            
            return traps
            
        except Exception as e:
            log.error("find_css_traps_failed", error=str(e))
            return []
    
    def _calculate_risk(self, report: HoneypotReport) -> float:
        """Calculate overall risk score."""
        score = 0.0
        
        # Hidden fields
        for field in report.hidden_fields:
            if field.is_hidden and field.is_suspicious:
                score += 0.5
            elif field.is_hidden or field.is_suspicious:
                score += 0.25
        
        # Trap links
        for link in report.trap_links:
            if link.is_suspicious:
                score += 0.3
            elif link.is_offscreen:
                score += 0.2
        
        # Decoy data
        score += len(report.decoy_data) * 0.15
        
        # CSS traps
        score += len(report.css_traps) * 0.3
        
        return min(1.0, score)
    
    def should_avoid(self, element: dict) -> bool:
        """Check if element should be avoided.
        
        Args:
            element: Element info dict
            
        Returns:
            True if element is a trap and should be avoided
        """
        # Hidden suspicious fields: always avoid
        if element.get("hidden") and element.get("suspicious"):
            return True
        
        # Trap links: always avoid
        if element.get("type") == "trap_link":
            return True
        
        return False


class HoneypotAwareActionRunner:
    """Action runner that avoids honeypots."""
    
    def __init__(self, page: Any):
        self._page = page
        self._detector = HoneypotDetector()
        self._report: HoneypotReport | None = None
    
    async def initialize(self) -> None:
        """Initialize by scanning the page for traps."""
        self._report = await self._detector.scan_page(self._page)
        log.debug("honeypot_scan_complete",
                  hidden_fields=len(self._report.hidden_fields),
                  trap_links=len(self._report.trap_links))
    
    async def safe_click(self, selector: str) -> bool:
        """Click element if it's not a honeypot.
        
        Args:
            selector: Element selector
            
        Returns:
            True if clicked successfully, False if skipped
        """
        if self._report is None:
            await self.initialize()
        
        # Check if selector matches any trap
        for field in self._report.hidden_fields:
            if field.name in selector or selector in field.name:
                log.warning("skipping_honeypot_field", selector=selector)
                return False
        
        for link in self._report.trap_links:
            if selector in link.href:
                log.warning("skipping_trap_link", selector=selector)
                return False
        
        # Safe to click
        await self._page.locator(selector).click()
        return True
    
    async def safe_fill(self, selector: str, value: str) -> bool:
        """Fill field if it's not a honeypot.
        
        Args:
            selector: Field selector
            value: Value to fill
            
        Returns:
            True if filled successfully, False if skipped
        """
        if self._report is None:
            await self.initialize()
        
        # Check if selector matches any hidden field
        for field in self._report.hidden_fields:
            if field.is_hidden and field.is_suspicious:
                if field.name in selector or selector in field.name:
                    log.warning("skipping_honeypot_input", selector=selector)
                    return False
        
        # Safe to fill
        await self._page.locator(selector).fill(value)
        return True
    
    @property
    def report(self) -> HoneypotReport:
        """Get honeypot detection report."""
        if self._report is None:
            raise RuntimeError("Not initialized. Call initialize() first.")
        return self._report