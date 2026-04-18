"""
Unified Detection Module

Consolidated detection from:
- axelo/core/failure_detector.py
- axelo/detection/signature_failure.py
- axelo/detection/honeypot_detector.py

Version: 2.0 (Unified)
Created: 2026-04-07
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

import structlog

log = structlog.get_logger()


# =============================================================================
# ERROR TYPES (from failure_detector.py)
# =============================================================================

class ErrorType:
    """Common error types"""
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    PARSE_ERROR = "parse_error"
    SIGNATURE_INVALID = "signature_invalid"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RecoveryStrategy:
    """A strategy for recovering from an error (from failure_detector.py)"""
    name: str
    error_types: list[str]
    apply: Callable  # Function to apply the fix
    
    description: str = ""
    success_rate: float = 0.5  # Historical success rate


@dataclass
class RecoveryResult:
    """Result of a recovery attempt (unified version)"""
    success: bool
    original_error: str = ""
    recovery_applied: str = ""
    new_code: str = ""
    confidence: float = 0.0
    suggestions: list[str] = field(default_factory=list)
    # Additional fields from signature_failure.py
    strategy: str = ""
    reason: str = ""
    requires_human: bool = False


@dataclass
class Diagnosis:
    """Diagnosis result of a failure (from signature_failure.py)"""
    indicators: dict[str, Any] = field(default_factory=dict)
    can_fix: bool = False
    recovery_priority: str = "low"
    known_pattern: str = ""
    suggested_fix: str = ""
    reason: str = ""
    
    def add_indicator(self, name: str, value: Any) -> None:
        self.indicators[name] = value
    
    @property
    def summary(self) -> str:
        return f"Diagnosis({self.reason}, fixable={self.can_fix})"


# =============================================================================
# UNIFIED FAILURE DETECTOR
# =============================================================================

class FailureDetector:
    """
    Detects failures in crawler execution.
    This is the main detector class combining functionality from multiple sources.
    """
    
    def __init__(self):
        self._error_patterns = self._build_error_patterns()
    
    def _build_error_patterns(self) -> dict:
        """Build patterns for detecting error types"""
        return {
            ErrorType.TIMEOUT: [
                r"timeout",
                r"timed out",
                r"ConnectTimeout",
                r"ReadTimeout",
            ],
            ErrorType.AUTH_ERROR: [
                r"401",
                r"403",
                r"unauthorized",
                r"forbidden",
                r"invalid.*token",
                r"invalid.*signature",
            ],
            ErrorType.RATE_LIMIT: [
                r"429",
                r"rate.*limit",
                r"too.*many.*request",
                r"throttle",
            ],
            ErrorType.PARSE_ERROR: [
                r"json.*decode",
                r"parse.*error",
                r"invalid.*json",
            ],
            ErrorType.SIGNATURE_INVALID: [
                r"signature.*invalid",
                r"sign.*error",
                r"hmac.*fail",
                r"crypto.*error",
            ],
            ErrorType.NETWORK_ERROR: [
                r"connection.*refused",
                r"connection.*reset",
                r"DNS.*error",
                r"network.*unreachable",
            ],
            ErrorType.SERVER_ERROR: [
                r"500",
                r"502",
                r"503",
                r"server.*error",
            ],
        }
    
    def detect_error_type(self, error_message: str) -> str:
        """Detect the type of error from error message"""
        error_lower = error_message.lower()
        
        for error_type, patterns in self._error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_lower, re.IGNORECASE):
                    return error_type
        
        return ErrorType.UNKNOWN
    
    def analyze_failure(self, error: str, context: Optional[dict] = None) -> Diagnosis:
        """Analyze a failure and provide diagnosis"""
        diagnosis = Diagnosis()
        
        # Detect error type
        error_type = self.detect_error_type(error)
        diagnosis.add_indicator("error_type", error_type)
        diagnosis.reason = f"Detected error type: {error_type}"
        
        # Determine if fixable
        fixable_types = [
            ErrorType.TIMEOUT,
            ErrorType.RATE_LIMIT,
            ErrorType.PARSE_ERROR,
        ]
        diagnosis.can_fix = error_type in fixable_types
        
        if diagnosis.can_fix:
            diagnosis.recovery_priority = "high"
            diagnosis.suggested_fix = f"Retry with adjusted {error_type} handling"
        
        return diagnosis
    
    def create_recovery_result(
        self,
        success: bool,
        original_error: str,
        recovery_applied: str = "",
    ) -> RecoveryResult:
        """Create a recovery result"""
        return RecoveryResult(
            success=success,
            original_error=original_error,
            recovery_applied=recovery_applied,
            confidence=0.8 if success else 0.0,
        )


# =============================================================================
# HONEY POT DETECTOR (from honeypot_detector.py)
# =============================================================================

@dataclass
class HoneypotDetectionResult:
    """Result of honeypot detection"""
    is_honeypot: bool
    confidence: float
    detected_traps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


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
    """Report of honeypot detection results (Playwright-based scan)."""
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
    """Detects honeypot traps in target websites.

    Provides two modes:
    - detect(html_content) — static HTML regex scan, returns HoneypotDetectionResult
    - scan_page(page)      — async Playwright live scan, returns HoneypotReport
    """

    # Common honeypot indicators (static HTML mode)
    HONEYPOT_PATTERNS = {
        "hidden_fields": [
            r'hidden.*value="[a-f0-9]{32,}"',
            r'<input[^>]*type="hidden"[^>]*name="(honeypot|trap|spider|bot)"',
        ],
        "fake_links": [
            r'<a[^>]*href="[^"]*(?:trap|honeypot|spider|bot)[^"]*"',
        ],
        "decoy_forms": [
            r'<form[^>]*action="[^"]*(?:submit|trap|honeypot)[^"]*"',
        ],
        "bot_detection_scripts": [
            r'if.*\(.*bot.*\).*\{\s*window\.location',
            r'document\.body\.style\.display\s*=\s*["\']none["\']',
        ],
    }

    # Suspicious field name patterns (Playwright mode)
    HONEYTOP_PATTERNS = [
        "honeypot", "trap", "bot", "spam", "fake", "hidden",
        "secret", "confirm", "anti", "check", "valid",
        "human", "robot", "test", "dummy", "空白",
    ]

    # Suspicious link patterns (Playwright mode)
    TRAP_LINK_PATTERNS = [
        "click", "track", "ad", "promo", "gift", "winner",
        "claim", "free", "offer", "deal", "win", "prize",
    ]

    def __init__(self):
        self._suspicious_names = [p.lower() for p in self.HONEYTOP_PATTERNS]
        self._trap_patterns = [p.lower() for p in self.TRAP_LINK_PATTERNS]

    # ------------------------------------------------------------------
    # Static HTML mode
    # ------------------------------------------------------------------

    def detect(self, html_content: str) -> HoneypotDetectionResult:
        """Detect honeypot traps in HTML"""
        detected_traps = []

        for trap_type, patterns in self.HONEYPOT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, html_content, re.IGNORECASE):
                    detected_traps.append(trap_type)

        is_honeypot = len(detected_traps) > 0
        confidence = min(0.5 + len(detected_traps) * 0.15, 0.95)

        recommendations = []
        if is_honeypot:
            recommendations.append("Consider using advanced browser fingerprinting")
            recommendations.append("Add randomized delays between requests")

        return HoneypotDetectionResult(
            is_honeypot=is_honeypot,
            confidence=confidence,
            detected_traps=detected_traps,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Playwright live-page mode
    # ------------------------------------------------------------------

    async def scan_page(self, page: Any) -> HoneypotReport:
        """Scan a live Playwright page and generate a HoneypotReport.

        Args:
            page: Playwright page object

        Returns:
            HoneypotReport with detected traps and risk score
        """
        report = HoneypotReport()

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

                        const isHidden =
                            style.display === 'none' ||
                            style.visibility === 'hidden' ||
                            style.opacity === '0' ||
                            rect.width === 0 ||
                            rect.height === 0 ||
                            parseFloat(style.opacity) < 0.01;

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

                        const isVisible =
                            style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 && rect.height > 0 &&
                            style.opacity !== '0' &&
                            parseFloat(style.opacity) > 0.01;

                        const isOffscreen =
                            rect.top > window.innerHeight ||
                            rect.left > window.innerWidth ||
                            rect.bottom < 0 ||
                            rect.right < 0;

                        const text = (el.textContent || '').toLowerCase();
                        const href = (el.href || '').toLowerCase();

                        const suspiciousPatterns = [
                            'click', 'track', 'ad', 'promo', 'gift',
                            'winner', 'claim', 'free', 'offer', 'deal'
                        ];

                        const isSuspicious =
                            suspiciousPatterns.some(p => text.includes(p)) ||
                            suspiciousPatterns.some(p => href.includes(p));

                        const isNavigation =
                            text.length > 50 ||
                            href.includes('/menu') ||
                            href.includes('/nav');

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
                    document.querySelectorAll('a, button, input[type="submit"]').forEach(el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();

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
        """Calculate overall risk score from a HoneypotReport."""
        score = 0.0

        for f in report.hidden_fields:
            if f.is_hidden and f.is_suspicious:
                score += 0.5
            elif f.is_hidden or f.is_suspicious:
                score += 0.25

        for link in report.trap_links:
            if link.is_suspicious:
                score += 0.3
            elif link.is_offscreen:
                score += 0.2

        score += len(report.decoy_data) * 0.15
        score += len(report.css_traps) * 0.3

        return min(1.0, score)

    def should_avoid(self, element: dict) -> bool:
        """Check if an element dict should be avoided (trap / hidden suspicious field).

        Args:
            element: Element info dict

        Returns:
            True if element is a trap and should be avoided
        """
        if element.get("hidden") and element.get("suspicious"):
            return True
        if element.get("type") == "trap_link":
            return True
        return False


class HoneypotAwareActionRunner:
    """Action runner that avoids honeypots (Playwright wrapper)."""

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

        for f in self._report.hidden_fields:
            if f.name in selector or selector in f.name:
                log.warning("skipping_honeypot_field", selector=selector)
                return False

        for link in self._report.trap_links:
            if selector in link.href:
                log.warning("skipping_trap_link", selector=selector)
                return False

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

        for f in self._report.hidden_fields:
            if f.is_hidden and f.is_suspicious:
                if f.name in selector or selector in f.name:
                    log.warning("skipping_honeypot_input", selector=selector)
                    return False

        await self._page.locator(selector).fill(value)
        return True

    @property
    def report(self) -> HoneypotReport:
        """Get honeypot detection report."""
        if self._report is None:
            raise RuntimeError("Not initialized. Call initialize() first.")
        return self._report


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def detect_error(error_message: str) -> str:
    """Quick helper to detect error type"""
    detector = FailureDetector()
    return detector.detect_error_type(error_message)


def diagnose_failure(error: str, context: Optional[dict] = None) -> Diagnosis:
    """Quick helper to diagnose failure"""
    detector = FailureDetector()
    return detector.analyze_failure(error, context)


def detect_honeypot(html_content: str) -> HoneypotDetectionResult:
    """Quick helper to detect honeypot"""
    detector = HoneypotDetector()
    return detector.detect(html_content)


# =============================================================================
# AUTO RECOVERY ENGINE (from core module)
# =============================================================================

class AutoRecoveryEngine:
    """
    Auto-recovery engine for fixing crawler failures.
    This is a simplified version - the full implementation is in the original module.
    """
    
    def __init__(self):
        self._failure_detector = FailureDetector()
    
    async def attempt_recovery(
        self,
        error: str,
        current_code: str,
        context: dict,
    ) -> RecoveryResult:
        """Attempt to recover from a failure"""
        # Analyze the error
        diagnosis = self._failure_detector.analyze_failure(error, context)
        
        if diagnosis.can_fix:
            # Apply fix based on diagnosis
            return RecoveryResult(
                success=True,
                original_error=error,
                recovery_applied=diagnosis.suggested_fix,
                confidence=0.7,
            )
        
        return RecoveryResult(
            success=False,
            original_error=error,
            recovery_applied="",
            confidence=0.0,
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Error types
    "ErrorType",
    # Data structures
    "RecoveryStrategy",
    "RecoveryResult",
    "Diagnosis",
    "HoneypotDetectionResult",
    # Detectors
    "FailureDetector",
    "HoneypotDetector",
    # Engine
    "AutoRecoveryEngine",
    # Utility functions
    "detect_error",
    "diagnose_failure",
    "detect_honeypot",
]