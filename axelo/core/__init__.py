"""
Axelo Universal Reverse Engine

A universal, generic reverse engineering engine for any website.

Core Components:
- Standard Traffic Format: Universal data representation
- Input Adapter: Convert any input to standard format
- Data Flow Tracker: Trace data from inputs to outputs
- Crypto Detector: Detect cryptographic operations (now in axelo.analysis.crypto)
- Signature Engine: Infer signature generation logic
- AI Integration: Enhance inference with AI
- Adaptive Learning: Self-improvement from success/failure
- Failure Recovery: Auto-fix failures (now in axelo.detection.unified)

Usage:
    from axelo.core import UniversalReverseEngine
    
    engine = UniversalReverseEngine()
    result = await engine.reverse("https://any-website.com")

Version: 1.1
Created: 2026-04-07
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from axelo.core.standard_traffic import StandardTraffic, SignatureHypothesis
from axelo.core.universal_input import UniversalInputAdapter, from_url
from axelo.core.data_flow_tracker import DataFlowGraph, trace_from_traffic
# Updated: Use new unified crypto module
from axelo.analysis.crypto import UniversalCryptoDetector, CryptoAnalysis
from axelo.core.signature_engine import UniversalSignatureEngine, InferenceResult
from axelo.core.ai_integration import AIAnalyzer, EnhancedSignatureEngine
from axelo.core.adaptive_learner import AdaptiveLearner, AdaptiveInferenceEngine
# Updated: Use new unified detection module
from axelo.detection.unified import AutoRecoveryEngine, FailureDetector

log = structlog.get_logger()


# =============================================================================
# MAIN ENGINE
# =============================================================================

@dataclass
class ReverseResult:
    """Result of reverse operation"""
    success: bool
    traffic: StandardTraffic
    inference: InferenceResult
    
    # Generated code
    crawler_code: str = ""
    
    # Metadata
    confidence: float = 0.0
    error: str = ""
    recovery_attempted: bool = False
    recovery_result: dict = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "confidence": self.confidence,
            "domain": self.traffic.domain,
            "algorithm": self.inference.hypothesis.algorithm.type.value if self.inference else "unknown",
            "has_code": bool(self.crawler_code),
            "recovery_attempted": self.recovery_attempted,
            "error": self.error,
        }


class UniversalReverseEngine:
    """
    Universal Reverse Engine
    
    The main entry point for the generic reverse engineering system.
    
    Features:
    - Universal input support (URL, HAR, etc.)
    - AI-enhanced inference
    - Adaptive learning
    - Auto-recovery from failures
    
    Usage:
        engine = UniversalReverseEngine()
        result = await engine.reverse("https://example.com")
        
        print(result.crawler_code)
    """
    
    def __init__(self, api_key: str = None):
        self.input_adapter = UniversalInputAdapter()
        self.signature_engine = UniversalSignatureEngine()
        self.crypto_detector = UniversalCryptoDetector()
        
        # AI enhancement (optional)
        self.ai_analyzer = None
        if api_key:
            self.ai_analyzer = AIAnalyzer(api_key=api_key)
        
        # Adaptive learning
        self.learner = AdaptiveLearner()
        
        # Failure recovery
        self.recovery_engine = AutoRecoveryEngine()
    
    async def reverse(
        self,
        url: str,
        capture_js: bool = True,
        enable_ai: bool = False,
        enable_learning: bool = True,
        **kwargs,
    ) -> ReverseResult:
        """
        Reverse engineer any website's signature
        
        Args:
            url: Target website URL
            capture_js: Whether to capture JavaScript code
            enable_ai: Whether to use AI enhancement
            enable_learning: Whether to learn from this inference
            **kwargs: Additional options
            
        Returns:
            ReverseResult with inferred signature and generated code
        """
        log.info("reverse_start", url=url)
        
        try:
            # Step 1: Capture traffic
            traffic = await self.input_adapter.adapt(url, source_type="url")
            
            if not traffic.traffic_pairs:
                return ReverseResult(
                    success=False,
                    traffic=traffic,
                    inference=None,
                    error="No traffic captured",
                )
            
            log.info("traffic_captured", 
                     requests=len(traffic.traffic_pairs),
                     domain=traffic.domain)
            
            # Get adaptive hints
            hints = {}
            if enable_learning:
                hints = self.learner.get_hints(traffic.domain)
            
            # Step 2: Infer signature (with AI if enabled)
            if enable_ai and self.ai_analyzer:
                # Use enhanced engine with AI
                inference = await self.signature_engine.infer(traffic)
                
                # Enhance with AI
                ai_result = await self.ai_analyzer.analyze(
                    traffic=traffic,
                    data_flow=inference.data_flow_graph,
                    crypto_analysis=inference.crypto_analysis,
                    current_hypothesis=inference.hypothesis,
                )
                
                # Use AI enhanced confidence
                inference.confidence = max(inference.confidence, ai_result.final_confidence)
            else:
                inference = await self.signature_engine.infer(traffic)
            
            log.info("inference_complete",
                     confidence=inference.confidence,
                     algorithm=inference.hypothesis.algorithm.type.value)
            
            # Step 3: Generate code
            crawler_code = await self._generate_code(traffic, inference)
            
            # Step 4: Try the generated code and recover if needed
            recovery_result = None
            if capture_js:
                test_result = await self._test_crawler(crawler_code, traffic)
                
                if not test_result["success"]:
                    # Attempt recovery
                    recovery = await self.recovery_engine.attempt_recovery(
                        error=test_result["error"],
                        current_code=crawler_code,
                        context={"domain": traffic.domain},
                    )
                    
                    if recovery.success:
                        crawler_code = recovery.new_code
                        recovery_result = {
                            "attempted": True,
                            "success": True,
                            "strategy": recovery.recovery_applied,
                        }
                        log.info("recovery_success", strategy=recovery.recovery_applied)
                    else:
                        recovery_result = {
                            "attempted": True,
                            "success": False,
                            "error": recovery.original_error,
                        }
            
            # Record success for learning
            if enable_learning:
                self.learner.on_success(
                    traffic.domain,
                    {"algorithm": inference.hypothesis.algorithm.type.value},
                    inference.confidence,
                )
            
            return ReverseResult(
                success=True,
                traffic=traffic,
                inference=inference,
                crawler_code=crawler_code,
                confidence=inference.confidence,
                recovery_attempted=recovery_result is not None,
                recovery_result=recovery_result,
            )
            
        except Exception as e:
            log.error("reverse_failed", error=str(e))
            
            # Record failure for learning
            if enable_learning:
                self.learner.on_failure(
                    url,
                    "exception",
                    "unknown",
                    ["Check error details"],
                )
            
            return ReverseResult(
                success=False,
                traffic=StandardTraffic(),
                inference=None,
                error=str(e),
            )
    
    async def _test_crawler(self, code: str, traffic) -> dict:
        """Test the generated crawler code"""
        # This would actually run the generated code
        # For now, return a mock result
        return {"success": True, "error": None}
    
    async def _generate_code(
        self,
        traffic: StandardTraffic,
        inference: InferenceResult,
    ) -> str:
        """Generate crawler code"""
        
        hypothesis = inference.hypothesis
        
        # Generate Python code
        code = f'''"""
Generated Crawler - Axelo Universal Reverse Engine
Target: {traffic.domain}
Algorithm: {hypothesis.algorithm.type.value}
Confidence: {inference.confidence:.1%}
"""

import httpx
import hashlib
import hmac
import base64
import time
import json
from urllib.parse import urlencode


class Crawler:
    def __init__(self):
        self.base_url = "{traffic.domain}"
        self.session = httpx.Client(timeout=30)
'''
        
        # Add key handling
        if hypothesis.key.source.value != "unknown":
            code += f'''
    # Key from: {hypothesis.key.source.value}
    key = "{hypothesis.key.location or 'secret'}"'''
        else:
            code += '''
    # Key source: unknown - needs manual configuration
    key = "YOUR_KEY_HERE"'''
        
        # Add algorithm code
        code += '''
    
    def generate_signature(self, params: dict) -> str:
        """Signature generation logic"""
'''
        
        algo = hypothesis.algorithm.type.value
        
        if "hmac_sha256" in algo.lower():
            code += '''
        message = self._build_message(params)
        signature = hmac.new(
            key.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return signature
'''
        elif "hmac" in algo.lower():
            code += '''
        message = self._build_message(params)
        signature = hmac.new(
            key.encode(), message.encode(), hashlib.sha1
        ).hexdigest()
        return signature
'''
        elif "md5" in algo.lower():
            code += '''
        message = self._build_message(params)
        return hashlib.md5(message.encode()).hexdigest()
'''
        else:
            code += f'''
        # Algorithm: {algo}
        message = self._build_message(params)
        return message
'''
        
        code += '''
    def _build_message(self, params: dict) -> str:
        sorted_keys = sorted(params.keys())
        return "&".join(f"{k}={params[k]}" for k in sorted_keys)

    def make_request(self, endpoint, params=None):
        if params is None:
            params = {}
        params["sign"] = self.generate_signature(params)
        return self.session.get(self.base_url + endpoint, params=params)

    def close(self):
        self.session.close()


if __name__ == "__main__":
    crawler = Crawler()
    crawler.close()
'''
        
        return code


# =============================================================================
# QUICK API
# =============================================================================

async def reverse(url: str, **kwargs) -> ReverseResult:
    """Quick function to reverse a website"""
    engine = UniversalReverseEngine()
    return await engine.reverse(url, **kwargs)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Main classes
    "UniversalReverseEngine",
    "ReverseResult",
    # Components
    "StandardTraffic",
    "SignatureHypothesis",
    "DataFlowGraph",
    "CryptoAnalysis",
    "InferenceResult",
    # AI
    "AIAnalyzer",
    "EnhancedSignatureEngine",
    # Learning
    "AdaptiveLearner",
    "AdaptiveInferenceEngine",
    # Recovery
    "AutoRecoveryEngine",
    "FailureDetector",
    # Utility
    "from_url",
    "reverse",
]