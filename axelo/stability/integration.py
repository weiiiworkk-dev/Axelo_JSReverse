"""Long-term stability integration module - brings all stability modules together."""
from __future__ import annotations

import structlog

log = structlog.get_logger()

# Re-export all stability modules for easy importing

# Behavior simulation
from axelo.behavior.mouse_simulator import (
    MouseMovementSimulator,
    KeyboardSimulator,
    ScrollSimulator,
    IdlePatternGenerator,
    create_behavior_simulator,
)

# Detection
from axelo.detection.honeypot_detector import (
    HoneypotDetector,
    HoneypotReport,
    HoneypotAwareActionRunner,
)
from axelo.detection.signature_failure import (
    SignatureFailureDetector,
    RecoveryResult,
    Diagnosis,
    RecoveryStrategyRegistry,
    create_failure_detector,
)

# Rate control
from axelo.rate_control.adaptive_limiter import (
    AdaptiveRateController,
    PacingModel,
    create_rate_controller,
)

# Fingerprint
from axelo.fingerprint.fingerprint_reinforcer import (
    DeviceFingerprintReinforcer,
    DeviceFingerprint,
    create_fingerprint_reinforcer,
)

# Learning
from axelo.learning.adaptive_learning import (
    AdaptiveLearningSystem,
    SuccessPatternDatabase,
    FailurePatternDatabase,
    create_learning_system,
)

# Pipeline integration
from axelo.pipeline.stages.behavior_runner import (
    BehaviorEnhancedActionRunner,
    create_behavior_runner,
)

# Browser integration
from axelo.browser.enhanced_driver import (
    EnhancedBrowserDriver,
    create_enhanced_driver,
)


__all__ = [
    # Behavior
    "MouseMovementSimulator",
    "KeyboardSimulator",
    "ScrollSimulator",
    "IdlePatternGenerator",
    "create_behavior_simulator",
    
    # Detection
    "HoneypotDetector",
    "HoneypotReport",
    "HoneypotAwareActionRunner",
    "SignatureFailureDetector",
    "RecoveryResult",
    "Diagnosis",
    "RecoveryStrategyRegistry",
    "create_failure_detector",
    
    # Rate Control
    "AdaptiveRateController",
    "PacingModel",
    "create_rate_controller",
    
    # Fingerprint
    "DeviceFingerprintReinforcer",
    "DeviceFingerprint",
    "create_fingerprint_reinforcer",
    
    # Learning
    "AdaptiveLearningSystem",
    "SuccessPatternDatabase",
    "FailurePatternDatabase",
    "create_learning_system",
    
    # Pipeline
    "BehaviorEnhancedActionRunner",
    "create_behavior_runner",
    
    # Browser
    "EnhancedBrowserDriver",
    "create_enhanced_driver",
]


# =============================================================================
# QUICK START
# =============================================================================

def get_stability_config() -> dict:
    """Get default stability configuration."""
    return {
        "behavior": {
            "enabled": True,
            "mouse_simulation": True,
            "keyboard_simulation": True,
            "scroll_simulation": True,
            "idle_generation": True,
        },
        "detection": {
            "honeypot_detection": True,
            "signature_failure_detection": True,
        },
        "rate_control": {
            "enabled": True,
            "strategy": "moderate",
        },
        "fingerprint": {
            "enabled": True,
            "canvas_fingerprint": True,
            "audio_fingerprint": True,
            "font_detection": True,
        },
        "learning": {
            "enabled": True,
            "record_success_patterns": True,
            "record_failure_patterns": True,
        },
    }


def create_integrated_stability_system(config: dict | None = None) -> "IntegratedStabilitySystem":
    """Create integrated stability system with all modules."""
    config = config or get_stability_config()
    return IntegratedStabilitySystem(config)


class IntegratedStabilitySystem:
    """
    Integrated stability system that combines all modules.
    
    This is the main entry point for using the stability enhancements.
    
    Usage:
        system = create_integrated_stability_system()
        
        # Use in crawler
        await system.on_request(url)
        await system.before_click(page, selector)
        await system.on_response(response)
        
        # Get learning insights
        strategy = system.get_strategy(domain)
    """
    
    def __init__(self, config: dict):
        self._config = config
        
        # Initialize behavior simulators
        if config.get("behavior", {}).get("enabled"):
            self._behavior = create_behavior_simulator()
        else:
            self._behavior = None
        
        # Initialize detection
        if config.get("detection", {}).get("honeypot_detection"):
            self._honeypot = HoneypotDetector()
        else:
            self._honeypot = None
            
        if config.get("detection", {}).get("signature_failure_detection"):
            self._signature_failure = create_failure_detector()
        else:
            self._signature_failure = None
        
        # Initialize rate control
        if config.get("rate_control", {}).get("enabled"):
            self._rate_controller = create_rate_controller(
                config.get("rate_control", {}).get("strategy", "moderate")
            )
        else:
            self._rate_controller = None
        
        # Initialize fingerprint
        if config.get("fingerprint", {}).get("enabled"):
            self._fingerprint = create_fingerprint_reinforcer()
        else:
            self._fingerprint = None
        
        # Initialize learning
        if config.get("learning", {}).get("enabled"):
            self._learning = create_learning_system()
        else:
            self._learning = None
    
    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------
    
    async def initialize(self, page: Any, domain: str) -> None:
        """
        Initialize stability system with page context.
        
        Args:
            page: Playwright page
            domain: Target domain for rate limiting
        """
        self._page = page
        self._domain = domain
        
        # Scan for honeypots if enabled
        if self._honeypot:
            try:
                self._honeypot_report = await self._honeypot.scan_page(page)
                if self._honeypot_report.has_traps:
                    log.warning("honeypot_detected_init",
                               hidden_fields=len(self._honeypot_report.hidden_fields),
                               trap_links=len(self._honeypot_report.trap_links))
            except Exception as e:
                log.warning("honeypot_scan_failed", error=str(e))
        
        log.info("stability_system_initialized", domain=domain)
    
    # -------------------------------------------------------------------------
    # Request Lifecycle Methods
    # -------------------------------------------------------------------------
    
    async def before_request(self, domain: str) -> None:
        """Called before making a request."""
        if self._rate_controller:
            await self._rate_controller.acquire(domain)
    
    def on_response(self, domain: str, response_time: float, status_code: int) -> None:
        """Called after receiving a response."""
        if self._rate_controller:
            self._rate_controller.on_response(domain, response_time, status_code)
    
    async def before_click(self, page, selector: str) -> bool:
        """
        Called before clicking an element.
        
        Returns:
            True if safe to click, False if honeypot detected
        """
        if not self._behavior:
            return True
        
        # Check honeypot
        if self._honeypot:
            report = await self._honeypot.scan_page(page)
            for field in report.hidden_fields:
                if field.name in selector:
                    return False
        
        # Use behavior simulation
        if self._behavior.get("mouse"):
            await self._behavior["mouse"].move_to_element(page, selector, click=True)
            return True
        
        return True
    
    async def before_type(self, page, selector: str, text: str) -> bool:
        """
        Called before typing into an element.
        
        Returns:
            True if safe to type, False if honeypot detected
        """
        if not self._behavior:
            return True
        
        # Check honeypot
        if self._honeypot:
            report = await self._honeypot.scan_page(page)
            for field in report.hidden_fields:
                if field.is_hidden and field.is_suspicious:
                    if field.name in selector:
                        return False
        
        # Use behavior simulation
        if self._behavior.get("keyboard"):
            await self._behavior["keyboard"].type_text(page, text, selector)
            return True
        
        return True
    
    async def on_failure(self, context: dict, error: str) -> None:
        """Called when a request fails."""
        if self._learning and context.get("domain"):
            # Create request context for learning
            from axelo.learning.adaptive_learning import RequestContext, RequestResult
            
            req_context = RequestContext(
                domain=context["domain"],
                url=context.get("url", ""),
                method=context.get("method", "GET"),
                headers=context.get("headers", {}),
                timestamp=context.get("timestamp", 0),
            )
            
            req_result = RequestResult(
                success=False,
                status_code=context.get("status_code", 0),
                response_time=context.get("response_time", 0),
                error=error,
            )
            
            await self._learning.learn_from_result(req_context, req_result)
    
    def get_strategy(self, domain: str) -> dict:
        """Get optimized strategy for domain."""
        if not self._learning:
            return {}
        
        from axelo.learning.adaptive_learning import RequestContext
        
        context = RequestContext(
            domain=domain,
            url="",
            method="GET",
            headers={},
            timestamp=0,
        )
        
        return self._learning.get_optimized_strategy(context)
    
    def get_domain_status(self, domain: str) -> dict:
        """Get learning status for domain."""
        if not self._learning:
            return {}
        
        return self._learning.get_domain_status(domain)
    
    @property
    def rate_controller(self):
        """Get rate controller."""
        return self._rate_controller
    
    @property
    def learning_system(self):
        """Get learning system."""
        return self._learning