"""
Universal Data Flow Tracker

Tracks data flow from inputs to outputs through JavaScript transformations.
This is a core component of the Universal Reverse Engine.

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import defaultdict

import structlog

from axelo.core.standard_traffic import (
    StandardTraffic,
    ParameterLocation,
    TrafficPair,
    RequestInfo,
)

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class DataNode:
    """A single node in the data flow graph"""
    id: str
    name: str
    location: ParameterLocation  # Where the data comes from
    value: Any = None
    node_type: str = "source"  # source, transform, sink
    
    # For source nodes
    is_generated: bool = False  # timestamp, nonce, etc.
    generation_method: Optional[str] = None
    
    # For transform nodes  
    transform_type: Optional[str] = None  # concat, encode, hash, etc.
    transform_code: Optional[str] = None  # code snippet
    
    # For sink nodes
    is_signature: bool = False
    output_location: Optional[ParameterLocation] = None


@dataclass
class DataEdge:
    """Edge connecting nodes in the data flow"""
    source_id: str
    target_id: str
    transform: Optional[str] = None  # What happens to the data
    confidence: float = 1.0


@dataclass
class DataFlowGraph:
    """Complete data flow graph"""
    nodes: dict[str, DataNode] = field(default_factory=dict)
    edges: list[DataEdge] = field(default_factory=list)
    
    # Input points (sources)
    input_nodes: list[str] = field(default_factory=list)
    
    # Output points (sinks)
    output_nodes: list[str] = field(default_factory=list)
    
    def add_node(self, node: DataNode):
        self.nodes[node.id] = node
        if node.node_type == "source":
            self.input_nodes.append(node.id)
        elif node.node_type == "sink":
            self.output_nodes.append(node.id)
    
    def add_edge(self, edge: DataEdge):
        self.edges.append(edge)
    
    def get_path(self, start_id: str, end_id: str) -> list[DataNode]:
        """Get path from start to end"""
        # Simple BFS
        visited = set()
        queue = [(start_id, [start_id])]
        
        while queue:
            node_id, path = queue.pop(0)
            
            if node_id == end_id:
                return [self.nodes[n] for n in path]
            
            if node_id in visited:
                continue
            visited.add(node_id)
            
            # Find next nodes
            for edge in self.edges:
                if edge.source_id == node_id:
                    queue.append((edge.target_id, path + [edge.target_id]))
        
        return []
    
    def get_all_signatures(self) -> list[DataNode]:
        """Get all signature sink nodes"""
        return [n for n in self.nodes.values() if n.is_signature]


# =============================================================================
# TRANSFORM DETECTOR
# =============================================================================

class TransformDetector:
    """
    Detects data transformations in JavaScript code
    """
    
    # Common transform patterns
    TRANSFORM_PATTERNS = {
        "concat": [
            r"\.concat\(",
            r"\+\s*['\"(]",  # String concatenation
            r"Array\.join\(",
        ],
        "encode_base64": [
            r"btoa\(",
            r"\.toBase64\(",
            r"CryptoJS\.enc\.Base64",
            r"Buffer\.from.*\.toString\('base64'\)",
        ],
        "decode_base64": [
            r"atob\(",
            r"\.fromBase64\(",
            r"Buffer\.from.*\.toString\('binary'\)",
        ],
        "encode_url": [
            r"encodeURIComponent\(",
            r"encodeURI\(",
        ],
        "encode_hex": [
            r"\.toHex\(",
            r"\.toString\(16\)",
            r"Number\(.*\)\.toString\(16\)",
        ],
        "json_stringify": [
            r"JSON\.stringify\(",
            r"\.stringify\(",
        ],
        "json_parse": [
            r"JSON\.parse\(",
        ],
        "hash_md5": [
            r"md5\(",
            r"\.md5\(",
            r"CryptoJS\.MD5",
            r"createHash\s*\(\s*['\"]md5['\"]",
        ],
        "hash_sha1": [
            r"sha1\(",
            r"\.sha1\(",
            r"CryptoJS\.SHA1",
        ],
        "hash_sha256": [
            r"sha256\(",
            r"\.sha256\(",
            r"CryptoJS\.SHA256",
        ],
        "hmac": [
            r"createHmac\(",
            r"\.hmac\(",
            r"CryptoJS\.Hmac",
        ],
        "aes_encrypt": [
            r"AES\.encrypt\(",
            r"\.encrypt\(",
            r"createCipher",
        ],
        "sort": [
            r"\.sort\(",
            r"Object\.keys.*sort",
        ],
        "to_lowercase": [
            r"\.toLowerCase\(",
        ],
        "to_uppercase": [
            r"\.toUpperCase\(",
        ],
        "trim": [
            r"\.trim\(",
        ],
        "replace": [
            r"\.replace\(",
            r"\.replaceAll\(",
        ],
        "split": [
            r"\.split\(",
        ],
        "substring": [
            r"\.substring\(",
            r"\.substr\(",
            r"\.slice\(",
        ],
    }
    
    def detect(self, js_code: str) -> list[dict]:
        """
        Detect transformations in JavaScript code
        
        Returns list of detected transforms
        """
        transforms = []
        
        for transform_type, patterns in self.TRANSFORM_PATTERNS.items():
            for pattern in patterns:
                matches = list(re.finditer(pattern, js_code, re.IGNORECASE))
                for match in matches:
                    # Get context (surrounding code)
                    start = max(0, match.start() - 50)
                    end = min(len(js_code), match.end() + 50)
                    context = js_code[start:end]
                    
                    transforms.append({
                        "type": transform_type,
                        "pattern": pattern,
                        "match": match.group(),
                        "position": match.start(),
                        "context": context.replace("\n", " "),
                    })
        
        # Sort by position
        transforms.sort(key=lambda x: x["position"])
        
        return transforms


# =============================================================================
# UNIVERSAL DATA FLOW TRACKER
# =============================================================================

class UniversalDataFlowTracker:
    """
    Universal Data Flow Tracker
    
    Traces data from inputs (URL params, headers, cookies) to outputs
    (signature headers, body fields) through JavaScript transformations.
    """
    
    def __init__(self):
        self.transform_detector = TransformDetector()
        self._input_patterns = self._build_input_patterns()
        self._output_patterns = self._build_output_patterns()
    
    def _build_input_patterns(self) -> dict:
        """Build patterns for detecting input sources"""
        return {
            "url_param": {
                "patterns": [r"URLSearchParams", r"\.searchParams", r"\?.*="],
                "keywords": ["params", "query", "search", "get"],
            },
            "header": {
                "patterns": [r"headers\[['\"]", r"\.setRequestHeader"],
                "keywords": ["header", "cookie"],
            },
            "cookie": {
                "patterns": [r"document\.cookie", r"Cookie", r"\.getCookie"],
                "keywords": ["cookie", "session"],
            },
            "body": {
                "patterns": [r"body\.", r"JSON\.stringify", r"formData"],
                "keywords": ["body", "post", "data"],
            },
            "timestamp": {
                "patterns": [r"Date\.now", r"\.getTime", r"performance\.now"],
                "keywords": ["timestamp", "time", "ts"],
                "generation": True,
            },
            "nonce": {
                "patterns": [r"Math\.random", r"UUID", r"crypto\.getRandomValues"],
                "keywords": ["nonce", "random", "uuid"],
                "generation": True,
            },
        }
    
    def _build_output_patterns(self) -> dict:
        """Build patterns for detecting output (signature) locations"""
        return {
            "header": {
                "patterns": [
                    r"setRequestHeader\s*\(\s*['\"]X-?[Ss]ign",
                    r"setRequestHeader\s*\(\s*['\"]X-?[Tt]oken",
                    r"headers\s*\[\s*['\"]X-?[Ss]ign",
                    r"headers\s*\[\s*['\"]X-?[Tt]oken",
                ],
                "location": ParameterLocation.HEADER,
            },
            "query": {
                "patterns": [
                    r"sign\s*=",
                    r"signature\s*=",
                    r"_sign\s*=",
                    r"url.*\+.*sign",
                ],
                "location": ParameterLocation.URL_QUERY,
            },
            "body": {
                "patterns": [
                    r"body\s*\.\s*sign\s*=",
                    r"data\s*\.\s*sign\s*=",
                    r"JSON\.stringify.*sign",
                ],
                "location": ParameterLocation.BODY_JSON,
            },
        }
    
    def trace(self, traffic: StandardTraffic) -> DataFlowGraph:
        """
        Trace data flow through the traffic
        
        Args:
            traffic: StandardTraffic with captured traffic
            
        Returns:
            DataFlowGraph with traced data flow
        """
        graph = DataFlowGraph()
        
        # Step 1: Identify input nodes
        input_nodes = self._identify_inputs(traffic)
        
        for node in input_nodes:
            graph.add_node(node)
        
        # Step 2: Identify output nodes
        output_nodes = self._identify_outputs(traffic)
        
        for node in output_nodes:
            graph.add_node(node)
        
        # Step 3: Analyze JavaScript for transforms
        transforms = self._extract_transforms(traffic)
        
        # Step 4: Create edges between nodes
        self._connect_nodes(graph, input_nodes, output_nodes, transforms)
        
        log.info("data_flow_traced", 
                 inputs=len(input_nodes), 
                 outputs=len(output_nodes),
                 transforms=len(transforms))
        
        return graph
    
    def _identify_inputs(self, traffic: StandardTraffic) -> list[DataNode]:
        """Identify all input data nodes"""
        nodes = []
        node_counter = 0
        
        # Analyze each traffic pair
        for pair in traffic.traffic_pairs:
            request = pair.request
            
            # URL parameters
            for param_name, param_value in request.url.query_params.items():
                node_id = f"input_{node_counter}"
                node_counter += 1
                
                # Check if it's generated (timestamp, nonce)
                is_generated, gen_method = self._check_if_generated(param_value, param_name)
                
                node = DataNode(
                    id=node_id,
                    name=param_name,
                    location=ParameterLocation.URL_QUERY,
                    value=param_value,
                    node_type="source",
                    is_generated=is_generated,
                    generation_method=gen_method,
                )
                nodes.append(node)
            
            # Headers
            for header_name, header_value in request.headers.raw.items():
                node_id = f"input_{node_counter}"
                node_counter += 1
                
                node = DataNode(
                    id=node_id,
                    name=header_name,
                    location=ParameterLocation.HEADER,
                    value=header_value[:50],  # Truncate long values
                    node_type="source",
                )
                nodes.append(node)
            
            # Body parameters
            if request.body:
                node_id = f"input_{node_counter}"
                node_counter += 1
                
                node = DataNode(
                    id=node_id,
                    name="request_body",
                    location=ParameterLocation.BODY_JSON,
                    value=request.body[:200],
                    node_type="source",
                )
                nodes.append(node)
        
        return nodes
    
    def _check_if_generated(self, value: str, name: str) -> tuple[bool, Optional[str]]:
        """Check if a value appears to be generated"""
        name_lower = name.lower()
        value_lower = str(value).lower()
        
        # Check name for generation indicators
        if any(k in name_lower for k in ["ts", "time", "_t", "timestamp"]):
            return True, "timestamp"
        if any(k in name_lower for k in ["nonce", "_n", "random"]):
            return True, "random"
        
        # Check value patterns
        # Timestamp: 13-digit number
        if re.match(r"^\d{13}$", str(value)):
            return True, "timestamp"
        # UUID pattern
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", str(value), re.I):
            return True, "uuid"
        
        return False, None
    
    def _identify_outputs(self, traffic: StandardTraffic) -> list[DataNode]:
        """Identify output (signature) nodes"""
        nodes = []
        node_counter = 0
        
        for pair in traffic.traffic_pairs:
            if not pair.contains_signature:
                continue
            
            request = pair.request
            
            # Check URL params
            for param_name in pair.signature_param_names:
                node_id = f"output_{node_counter}"
                node_counter += 1
                
                node = DataNode(
                    id=node_id,
                    name=param_name,
                    location=ParameterLocation.URL_QUERY,
                    value=request.url.query_params.get(param_name, "")[:50],
                    node_type="sink",
                    is_signature=True,
                    output_location=ParameterLocation.URL_QUERY,
                )
                nodes.append(node)
            
            # Check headers for signature
            signature_headers = [
                "X-Sign", "X-Signature", "X-Token", "X-Api-Key", 
                "Authorization", "X-Check"
            ]
            for header_name in signature_headers:
                header_value = request.headers.get(header_name)
                if header_value:
                    node_id = f"output_{node_counter}"
                    node_counter += 1
                    
                    node = DataNode(
                        id=node_id,
                        name=header_name,
                        location=ParameterLocation.HEADER,
                        value=header_value[:50],
                        node_type="sink",
                        is_signature=True,
                        output_location=ParameterLocation.HEADER,
                    )
                    nodes.append(node)
        
        return nodes
    
    def _extract_transforms(self, traffic: StandardTraffic) -> list[dict]:
        """Extract transformations from JavaScript code"""
        all_transforms = []
        
        for bundle in traffic.js_bundles:
            transforms = self.transform_detector.detect(bundle.content)
            for t in transforms:
                t["bundle_url"] = bundle.url
            all_transforms.extend(transforms)
        
        return all_transforms
    
    def _connect_nodes(
        self,
        graph: DataFlowGraph,
        input_nodes: list[DataNode],
        output_nodes: list[DataNode],
        transforms: list[dict],
    ):
        """Connect input and output nodes based on transforms"""
        
        # Simple heuristic: connect inputs to outputs if they appear in same transform
        # This is a simplified version - full implementation would need more analysis
        
        if not input_nodes or not output_nodes:
            return
        
        # Create edges between all inputs and outputs (with low confidence)
        # Real implementation would analyze transforms to determine actual connections
        for input_node in input_nodes:
            for output_node in output_nodes:
                # Check if names suggest connection
                confidence = 0.1  # Low confidence by default
                
                # Check if input appears in signature output
                if input_node.name.lower() in output_node.name.lower():
                    confidence = 0.3
                
                # Check for transformation patterns
                if transforms:
                    # Find transforms between them
                    for transform in transforms:
                        # Heuristic: transform might connect input to output
                        confidence = max(confidence, 0.2)
                
                if confidence > 0.1:
                    edge = DataEdge(
                        source_id=input_node.id,
                        target_id=output_node.id,
                        transform="unknown",
                        confidence=confidence,
                    )
                    graph.add_edge(edge)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def trace_from_traffic(traffic: StandardTraffic) -> DataFlowGraph:
    """Quick helper to trace data flow"""
    tracker = UniversalDataFlowTracker()
    return tracker.trace(traffic)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "DataNode",
    "DataEdge", 
    "DataFlowGraph",
    "TransformDetector",
    "UniversalDataFlowTracker",
    "trace_from_traffic",
]