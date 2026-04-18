"""
Universal Signature Inference Engine

The core engine that automatically infers signature generation logic.
Combines data flow analysis, crypto detection, and AI analysis.

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import structlog

from axelo.core.standard_traffic import (
    StandardTraffic,
    SignatureHypothesis,
    SignatureAlgorithm,
    SignatureType,
    SignatureInput,
    SignatureKey,
    SignatureOutput,
    ParameterLocation,
    KeySource,
)
from axelo.core.data_flow_tracker import (
    UniversalDataFlowTracker,
    DataFlowGraph,
)
from axelo.analysis.crypto import (
    UniversalCryptoDetector,
    CryptoAnalysis,
    CryptoAlgorithm,
    CryptoType,
)

log = structlog.get_logger()


# =============================================================================
# INFERENCE RESULT
# =============================================================================

@dataclass
class InferenceResult:
    """Result of signature inference"""
    hypothesis: SignatureHypothesis
    data_flow_graph: Optional[DataFlowGraph] = None
    crypto_analysis: Optional[CryptoAnalysis] = None
    
    # Metadata
    confidence: float = 0.0
    processing_time: float = 0.0
    algorithms_considered: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "hypothesis": self.hypothesis.to_dict(),
            "confidence": self.confidence,
            "algorithms": self.algorithms_considered,
            "warnings": self.warnings,
        }


# =============================================================================
# SIGNATURE INFERENCE ENGINE
# =============================================================================

class UniversalSignatureEngine:
    """
    Universal Signature Inference Engine
    
    Automatically infers signature generation logic from traffic data.
    
    This is the core component of the Universal Reverse Engine.
    """
    
    def __init__(self):
        self.data_flow_tracker = UniversalDataFlowTracker()
        self.crypto_detector = UniversalCryptoDetector()
        self._initialize_heuristics()
    
    def _initialize_heuristics(self):
        """Initialize heuristic rules"""
        
        # Map crypto algorithms to signature types
        self._algorithm_to_signature_type = {
            "hmac_md5": SignatureType.HMAC_MD5,
            "hmac_sha1": SignatureType.HMAC_SHA1,
            "hmac_sha256": SignatureType.HMAC_SHA256,
            "hmac_sha512": SignatureType.HMAC_SHA512,
            "md5": SignatureType.CUSTOM_HASH,
            "sha256": SignatureType.CUSTOM_HASH,
            "aes_cbc": SignatureType.AES_CBC,
            "aes_gcm": SignatureType.AES_GCM,
            "rsa_pkcs1": SignatureType.RSA_PKCS1,
        }
        
        # Common signature parameter names
        self._sign_param_names = [
            "sign", "signature", "_sign", "x_sign", "sign_data",
            "token", "_t", "ts", "timestamp", "nonce",
        ]
        
        # Common signature header names
        self._sign_header_names = [
            "X-Sign", "X-Signature", "X-Token", "X-Api-Key",
            "Authorization", "X-Check", "X-Validate", "X-Credential",
        ]
    
    async def infer(self, traffic: StandardTraffic) -> InferenceResult:
        """
        Infer signature logic from traffic
        
        Args:
            traffic: StandardTraffic with captured traffic and JS
            
        Returns:
            InferenceResult with inferred signature hypothesis
        """
        import time
        start_time = time.time()
        
        log.info("signature_inference_start", domain=traffic.domain)
        
        # Step 1: Data flow analysis
        data_flow = self.data_flow_tracker.trace(traffic)
        
        # Step 2: Crypto detection from JS
        crypto_analysis = self._analyze_crypto(traffic)
        
        # Step 3: Build hypothesis
        hypothesis = self._build_hypothesis(traffic, data_flow, crypto_analysis)
        
        # Step 4: Calculate confidence
        confidence = self._calculate_confidence(hypothesis, data_flow, crypto_analysis)
        
        # Step 5: Add evidence
        hypothesis.confidence = confidence
        hypothesis.evidence = self._collect_evidence(
            traffic, data_flow, crypto_analysis
        )
        
        processing_time = time.time() - start_time
        
        log.info("signature_inference_complete",
                  confidence=confidence,
                  time=processing_time,
                  algorithm=hypothesis.algorithm.type.value)
        
        return InferenceResult(
            hypothesis=hypothesis,
            data_flow_graph=data_flow,
            crypto_analysis=crypto_analysis,
            confidence=confidence,
            processing_time=processing_time,
            algorithms_considered=[
                a.value for a, _ in crypto_analysis.likely_algorithms[:5]
            ],
        )
    
    def _analyze_crypto(self, traffic: StandardTraffic) -> Optional[CryptoAnalysis]:
        """Analyze crypto operations in JS bundles"""
        if not traffic.js_bundles:
            return None
        
        # Analyze all JS bundles
        all_operations = []
        
        for bundle in traffic.js_bundles:
            analysis = self.crypto_detector.detect(bundle.content)
            all_operations.extend(analysis.operations)
        
        if not all_operations:
            return None
        
        # Merge results
        import copy
        combined = copy.deepcopy(all_operations[0].__class__.__bases__[0].__annotations__)
        
        # For now, return first bundle analysis
        return self.crypto_detector.detect(traffic.js_bundles[0].content)
    
    def _build_hypothesis(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
    ) -> SignatureHypothesis:
        """Build signature hypothesis"""
        
        # Determine algorithm
        algorithm = self._determine_algorithm(crypto_analysis)
        
        # Determine inputs
        inputs = self._determine_inputs(traffic, data_flow)
        
        # Determine key
        key = self._determine_key(traffic, crypto_analysis, data_flow)
        
        # Determine output
        output = self._determine_output(traffic, data_flow)
        
        # Determine construction steps
        steps = self._determine_steps(traffic, data_flow, crypto_analysis)
        
        return SignatureHypothesis(
            algorithm=algorithm,
            inputs=inputs,
            key=key,
            output=output,
            construction_steps=steps,
            confidence=0.0,  # Will be set later
        )
    
    def _determine_algorithm(
        self,
        crypto_analysis: Optional[CryptoAnalysis],
    ) -> SignatureAlgorithm:
        """Determine signature algorithm"""
        
        if not crypto_analysis or not crypto_analysis.likely_algorithms:
            # Fallback to unknown
            return SignatureAlgorithm.unknown(0.3)
        
        # Get top algorithm
        top_algo, confidence = crypto_analysis.likely_algorithms[0]
        
        # Convert to signature type
        sig_type = self._algorithm_to_signature_type.get(
            top_algo.value, SignatureType.UNKNOWN
        )
        
        return SignatureAlgorithm(
            type=sig_type,
            confidence=confidence,
            variant=top_algo.value,
        )
    
    def _determine_inputs(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
    ) -> list[SignatureInput]:
        """Determine signature inputs"""
        inputs = []
        
        # Get signature parameters from traffic
        for pair in traffic.traffic_pairs:
            if not pair.contains_signature:
                continue
            
            request = pair.request
            
            # URL parameters that are NOT signature parameters
            for param_name, param_value in request.url.query_params.items():
                if param_name not in pair.signature_param_names:
                    is_generated, gen_method = self._check_generated(param_value, param_name)
                    
                    inputs.append(SignatureInput(
                        name=param_name,
                        location=ParameterLocation.URL_QUERY,
                        value=str(param_value)[:100],
                        is_generated=is_generated,
                        generation_method=gen_method,
                    ))
            
            # Headers
            for header_name, header_value in request.headers.raw.items():
                if not any(s in header_name.lower() for s in ["sign", "token", "key"]):
                    inputs.append(SignatureInput(
                        name=header_name,
                        location=ParameterLocation.HEADER,
                        value=str(header_value)[:100],
                    ))
        
        # Deduplicate by name
        seen = {}
        unique_inputs = []
        for inp in inputs:
            if inp.name not in seen:
                seen[inp.name] = True
                unique_inputs.append(inp)
        
        return unique_inputs
    
    def _check_generated(self, value: str, name: str) -> tuple[bool, Optional[str]]:
        """Check if value is generated"""
        import re
        
        name_lower = name.lower()
        value_str = str(value)
        
        # Name-based detection
        if any(k in name_lower for k in ["ts", "time", "timestamp"]):
            return True, "timestamp"
        if any(k in name_lower for k in ["nonce", "random", "_n"]):
            return True, "random"
        
        # Value-based detection
        if re.match(r"^\d{13}$", value_str):
            return True, "timestamp"
        if re.match(r"^\d{10}$", value_str):
            return True, "timestamp"
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value_str, re.I):
            return True, "uuid"
        
        return False, None
    
    def _determine_key(
        self,
        traffic: StandardTraffic,
        crypto_analysis: Optional[CryptoAnalysis],
        data_flow: DataFlowGraph,
    ) -> SignatureKey:
        """Determine signature key source"""
        
        # Try to find key from crypto analysis
        if crypto_analysis and crypto_analysis.key_sources:
            source = crypto_analysis.key_sources[0]
            return SignatureKey(
                source=self._map_source_type(source.source_type),
                location=source.location,
            )
        
        # Try to find static key in JS
        if traffic.js_bundles:
            for bundle in traffic.js_bundles:
                # Look for common key patterns
                import re
                
                key_patterns = [
                    r"app[Ks]ey\s*=\s*['\"]([^'\"]+)['\"]",
                    r"app[Ss]ecret\s*=\s*['\"]([^'\"]+)['\"]",
                    r"secret\s*=\s*['\"]([^'\"]+)['\"]",
                ]
                
                for pattern in key_patterns:
                    match = re.search(pattern, bundle.content)
                    if match:
                        return SignatureKey(
                            source=KeySource.STATIC_CODE,
                            location="JS bundle",
                            value=match.group(1)[:20],
                        )
        
        # Default to unknown
        return SignatureKey(source=KeySource.UNKNOWN)
    
    def _map_source_type(self, source_type: str) -> KeySource:
        """Map crypto detector source type to our type"""
        mapping = {
            "static": KeySource.STATIC_CODE,
            "dynamic_cookie": KeySource.DYNAMIC_COOKIE,
            "dynamic_header": KeySource.DYNAMIC_HEADER,
            "dynamic_response": KeySource.DYNAMIC_RESPONSE,
        }
        return mapping.get(source_type, KeySource.UNKNOWN)
    
    def _determine_output(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
    ) -> SignatureOutput:
        """Determine where signature is placed"""
        
        for pair in traffic.traffic_pairs:
            if not pair.contains_signature:
                continue
            
            request = pair.request
            
            # Check URL params
            if pair.signature_param_names:
                return SignatureOutput(
                    location=ParameterLocation.URL_QUERY,
                    name=pair.signature_param_names[0],
                )
            
            # Check headers
            for header_name in self._sign_header_names:
                if request.headers.has(header_name):
                    return SignatureOutput(
                        location=ParameterLocation.HEADER,
                        name=header_name,
                    )
        
        # Default
        return SignatureOutput(
            location=ParameterLocation.URL_QUERY,
            name="sign",
        )
    
    def _determine_steps(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
    ) -> list[str]:
        """Determine signature construction steps"""
        steps = []
        
        # Add crypto operations
        if crypto_analysis:
            for algo, conf in crypto_analysis.likely_algorithms[:3]:
                steps.append(f"使用 {algo.value} 进行加密")
        
        # Add encoding steps
        steps.append("收集输入参数")
        steps.append("按规则排序")
        steps.append("拼接字符串")
        
        # Add output step
        if crypto_analysis and any(
            op.crypto_type == CryptoType.ENCODING 
            for op in crypto_analysis.operations
        ):
            steps.append("Base64/HEX 编码")
        
        steps.append("添加到请求")
        
        return steps
    
    def _calculate_confidence(
        self,
        hypothesis: SignatureHypothesis,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
    ) -> float:
        """Calculate overall confidence"""
        
        confidence = 0.0
        factors = []
        
        # Factor 1: Algorithm confidence
        if hypothesis.algorithm.type != SignatureType.UNKNOWN:
            confidence += hypothesis.algorithm.confidence * 0.4
            factors.append(f"algorithm: {hypothesis.algorithm.confidence}")
        
        # Factor 2: Key source
        if hypothesis.key.source != KeySource.UNKNOWN:
            confidence += 0.2
            factors.append("key_found")
        
        # Factor 3: Data flow
        if len(data_flow.input_nodes) > 0:
            confidence += 0.1
            factors.append(f"inputs: {len(data_flow.input_nodes)}")
        
        # Factor 4: Crypto detection
        if crypto_analysis and crypto_analysis.operations:
            confidence += 0.2
            factors.append(f"crypto_ops: {len(crypto_analysis.operations)}")
        
        # Factor 5: Construction steps
        if len(hypothesis.construction_steps) >= 3:
            confidence += 0.1
        
        log.info("confidence_calculation", 
                  confidence=min(confidence, 1.0),
                  factors=factors)
        
        return min(confidence, 1.0)
    
    def _collect_evidence(
        self,
        traffic: StandardTraffic,
        data_flow: DataFlowGraph,
        crypto_analysis: Optional[CryptoAnalysis],
    ) -> list[str]:
        """Collect evidence for the hypothesis"""
        evidence = []
        
        # Traffic evidence
        if traffic.traffic_pairs:
            api_count = sum(1 for p in traffic.traffic_pairs if p.is_api_call)
            evidence.append(f"捕获 {len(traffic.traffic_pairs)} 个请求, {api_count} 个 API 调用")
        
        # Signature evidence
        sig_count = sum(1 for p in traffic.traffic_pairs if p.contains_signature)
        if sig_count > 0:
            evidence.append(f"检测到 {sig_count} 个包含签名的请求")
        
        # Crypto evidence
        if crypto_analysis:
            evidence.append(f"JS 中检测到 {len(crypto_analysis.operations)} 个加密操作")
        
        # Data flow evidence
        evidence.append(f"数据流图: {len(data_flow.input_nodes)} 输入 → {len(data_flow.output_nodes)} 输出")
        
        return evidence


# =============================================================================
# QUICK API
# =============================================================================

async def infer_signature(traffic: StandardTraffic) -> InferenceResult:
    """Quick helper to infer signature"""
    engine = UniversalSignatureEngine()
    return await engine.infer(traffic)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "InferenceResult",
    "UniversalSignatureEngine",
    "infer_signature",
]