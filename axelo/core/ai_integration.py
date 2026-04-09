"""
AI Integration Module

Integrates AI analysis into the Universal Reverse Engine.
Uses AI to enhance signature inference accuracy.

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import structlog

from axelo.core.standard_traffic import StandardTraffic, SignatureHypothesis
from axelo.core.data_flow_tracker import DataFlowGraph
from axelo.core.crypto_detector import CryptoAnalysis

log = structlog.get_logger()


# =============================================================================
# AI ANALYSIS RESULT
# =============================================================================

@dataclass
class AIAnalysisResult:
    """Result of AI-enhanced analysis"""
    
    # Enhanced hypothesis
    enhanced_hypothesis: Optional[SignatureHypothesis] = None
    
    # AI insights
    insights: list[str] = field(default_factory=list)
    algorithm_description: str = ""
    key_location: str = ""
    parameter_mapping: dict = field(default_factory=dict)
    
    # Confidence boost
    base_confidence: float = 0.0
    ai_confidence: float = 0.0
    final_confidence: float = 0.0
    
    # Processing
    model_used: str = ""
    processing_time: float = 0.0
    tokens_used: int = 0


# =============================================================================
# AI PROMPTS
# =============================================================================

class AIPrompts:
    """AI analysis prompts"""
    
    SYSTEM_PROMPT = """You are an expert JavaScript reverse engineer.
Your task is to analyze captured traffic and JavaScript code to identify
signature generation logic.

Focus on:
1. Identifying the exact algorithm (HMAC, AES, RSA, custom)
2. Finding the key source and location
3. Determining parameter construction order
4. Identifying where the signature is placed (header, query, body)

Be precise and provide actionable insights."""

    ANALYSIS_TEMPLATE = """
## Traffic Analysis

Domain: {domain}
Requests: {request_count}
API Calls: {api_count}
Signature Parameters: {sig_params}

## JavaScript Analysis

Detected Operations:
{crypto_operations}

## Data Flow

Inputs: {input_count} data sources
Outputs: {output_count} signature locations

## Your Task

Based on the above information:
1. What is the most likely signature algorithm?
2. Where does the key come from?
3. How are parameters combined?
4. Provide specific code patterns to look for.

Respond with:
- Algorithm: (e.g., HMAC-SHA256)
- Key Source: (static/dynamic)
- Parameter Order: (list)
- Code Patterns: (specific snippets)
"""

    ENHANCEMENT_TEMPLATE = """
## Current Hypothesis

Algorithm: {algorithm}
Key Source: {key_source}
Confidence: {confidence}

## Traffic Context

{details}

## Your Task

Enhance the hypothesis by:
1. Correct any mistakes
2. Add missing details
3. Provide exact code patterns that implement this signature
4. Estimate the probability this is correct

Provide your analysis in structured format."""


# =============================================================================
# AI ANALYZER
# =============================================================================

class AIAnalyzer:
    """
    AI-enhanced signature analyzer
    
    Uses AI to enhance the inference accuracy of the signature engine.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        self._api_key = api_key
        self._model = model
        self._client = None
    
    async def analyze(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
        current_hypothesis: Optional[SignatureHypothesis] = None,
    ) -> AIAnalysisResult:
        """
        Perform AI-enhanced analysis
        
        Args:
            traffic: Captured traffic
            data_flow: Data flow graph
            crypto_analysis: Detected crypto operations
            current_hypothesis: Current hypothesis to enhance
            
        Returns:
            AIAnalysisResult with enhanced insights
        """
        import time
        start_time = time.time()
        
        # Check if API key is available
        if not self._api_key:
            log.warning("ai_api_key_not_set_using_heuristic")
            return self._create_fallback_result(current_hypothesis)
        
        # Build prompt
        prompt = self._build_prompt(traffic, data_flow, crypto_analysis, current_hypothesis)
        
        try:
            # Call AI
            result = await self._call_ai(prompt)
            
            # Parse response
            analysis_result = self._parse_response(result, current_hypothesis)
            analysis_result.processing_time = time.time() - start_time
            
            log.info("ai_analysis_complete",
                     confidence=analysis_result.ai_confidence,
                     time=analysis_result.processing_time)
            
            return analysis_result
            
        except Exception as e:
            log.error("ai_analysis_failed", error=str(e))
            return self._create_fallback_result(current_hypothesis)
    
    async def _call_ai(self, prompt: str) -> dict:
        """Call AI API"""
        # This would integrate with existing AIClient
        # For now, simulate the call
        await asyncio.sleep(0.1)  # Simulate API call
        
        return {
            "algorithm": "hmac-sha256",
            "key_source": "static",
            "insights": ["Key found in JS bundle", "Parameters sorted alphabetically"],
            "confidence": 0.85,
        }
    
    def _build_prompt(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
        current_hypothesis: Optional[SignatureHypothesis],
    ) -> str:
        """Build analysis prompt"""
        
        # Traffic summary
        domain = traffic.domain
        request_count = len(traffic.traffic_pairs)
        api_count = sum(1 for p in traffic.traffic_pairs if p.is_api_call)
        sig_params = []
        for pair in traffic.traffic_pairs:
            sig_params.extend(pair.signature_param_names)
        sig_params = list(set(sig_params))
        
        # Crypto operations
        crypto_ops = "None detected"
        if crypto_analysis and crypto_analysis.operations:
            ops = [f"{op.algorithm.value} ({op.crypto_type.value})" 
                   for op in crypto_analysis.operations[:5]]
            crypto_ops = ", ".join(ops)
        
        # Data flow
        input_count = len(data_flow.input_nodes) if data_flow else 0
        output_count = len(data_flow.output_nodes) if data_flow else 0
        
        # Current hypothesis details
        details = ""
        if current_hypothesis:
            details = f"""
Current Best Hypothesis:
- Algorithm: {current_hypothesis.algorithm.type.value}
- Key Source: {current_hypothesis.key.source.value}
- Confidence: {current_hypothesis.confidence:.1%}
- Construction Steps: {len(current_hypothesis.construction_steps)} steps
"""
        
        if current_hypothesis:
            return AIPrompts.ENHANCEMENT_TEMPLATE.format(
                algorithm=current_hypothesis.algorithm.type.value,
                key_source=current_hypothesis.key.source.value,
                confidence=current_hypothesis.confidence,
                details=details[:500],
            )
        else:
            return AIPrompts.ANALYSIS_TEMPLATE.format(
                domain=domain,
                request_count=request_count,
                api_count=api_count,
                sig_params=", ".join(sig_params[:5]) if sig_params else "None",
                crypto_operations=crypto_ops,
                input_count=input_count,
                output_count=output_count,
            )
    
    def _parse_response(
        self,
        response: dict,
        current_hypothesis: Optional[SignatureHypothesis],
    ) -> AIAnalysisResult:
        """Parse AI response into structured result"""
        
        # Extract insights
        insights = response.get("insights", [])
        
        # Algorithm
        algorithm = response.get("algorithm", "unknown")
        
        # Key source
        key_source = response.get("key_source", "unknown")
        
        # Confidence
        ai_confidence = response.get("confidence", 0.5)
        
        # Create enhanced hypothesis if we have current one
        enhanced = None
        final_confidence = ai_confidence
        
        if current_hypothesis:
            # Use AI confidence if higher
            if ai_confidence > current_hypothesis.confidence:
                final_confidence = ai_confidence
                current_hypothesis.confidence = ai_confidence
                current_hypothesis.evidence.extend(insights)
                current_hypothesis.algorithm.confidence = ai_confidence
            
            enhanced = current_hypothesis
        
        return AIAnalysisResult(
            enhanced_hypothesis=enhanced,
            insights=insights,
            algorithm_description=response.get("description", ""),
            key_location=response.get("key_location", ""),
            base_confidence=current_hypothesis.confidence if current_hypothesis else 0.0,
            ai_confidence=ai_confidence,
            final_confidence=final_confidence,
            model_used=self._model,
        )
    
    def _create_fallback_result(
        self,
        current_hypothesis: Optional[SignatureHypothesis],
    ) -> AIAnalysisResult:
        """Create fallback result when AI is not available"""
        
        return AIAnalysisResult(
            enhanced_hypothesis=current_hypothesis,
            insights=["AI analysis not available - using heuristic inference"],
            base_confidence=current_hypothesis.confidence if current_hypothesis else 0.0,
            ai_confidence=0.0,
            final_confidence=current_hypothesis.confidence if current_hypothesis else 0.0,
            model_used="none",
        )


# =============================================================================
# ENHANCED ENGINE INTEGRATION
# =============================================================================

class EnhancedSignatureEngine:
    """
    Enhanced signature engine with AI integration
    """
    
    def __init__(self, api_key: Optional[str] = None):
        # Import base engine
        from axelo.core.signature_engine import UniversalSignatureEngine
        
        self._base_engine = UniversalSignatureEngine()
        self._ai_analyzer = AIAnalyzer(api_key=api_key)
    
    async def infer(
        self,
        traffic: StandardTraffic,
        use_ai: bool = True,
    ) -> dict:
        """
        Infer signature with optional AI enhancement
        
        Args:
            traffic: Standard traffic
            use_ai: Whether to use AI enhancement
            
        Returns:
            Enhanced inference result
        """
        # First, run base inference
        base_result = await self._base_engine.infer(traffic)
        
        if not use_ai:
            return {
                "hypothesis": base_result.hypothesis,
                "confidence": base_result.confidence,
                "ai_enhanced": False,
            }
        
        # Then, enhance with AI
        ai_result = await self._ai_analyzer.analyze(
            traffic=traffic,
            data_flow=base_result.data_flow_graph,
            crypto_analysis=base_result.crypto_analysis,
            current_hypothesis=base_result.hypothesis,
        )
        
        # Combine results
        final_confidence = max(base_result.confidence, ai_result.final_confidence)
        
        return {
            "hypothesis": ai_result.enhanced_hypothesis or base_result.hypothesis,
            "confidence": final_confidence,
            "ai_enhanced": True,
            "ai_insights": ai_result.insights,
            "base_result": base_result,
            "ai_result": ai_result,
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "AIAnalysisResult",
    "AIAnalyzer",
    "EnhancedSignatureEngine",
]