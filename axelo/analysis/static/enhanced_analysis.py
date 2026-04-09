"""
Enhanced Static Analysis Module

Provides advanced static analysis capabilities:
- Taint analysis (track data flow)
- Control flow analysis
- Obfuscation detection
- Code similarity analysis

Version: 1.0
Created: 2026-04-06
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# TAINT ANALYSIS
# =============================================================================

@dataclass
class TaintSource:
    """Represents a source of tainted data"""
    name: str
    type: str  # "user_input", "random", "timestamp", "cookie", "storage", "response"
    location: str  # Line number or function name
    confidence: float = 1.0


@dataclass
class TaintSink:
    """Represents where tainted data is used"""
    name: str
    type: str  # "crypto", "network", "storage", "output"
    location: str
    field: Optional[str] = None


@dataclass
class TaintPath:
    """Represents a path from source to sink"""
    source: TaintSource
    sink: TaintSink
    transformations: list[str] = field(default_factory=list)  # hash, base64, concat, etc.
    confidence: float = 1.0


class TaintAnalyzer:
    """
    Analyzes code for taint propagation.
    
    Tracks how data flows from sources (user input, random, timestamp)
    to sinks (crypto operations, network requests).
    """
    
    # Known taint sources
    SOURCE_PATTERNS = {
        "user_input": [
            r"input\.",
            r"form\.",
            r"\$\(.*\)\.val\(",
            r"document\.getElementById",
            r"prompt\(",
        ],
        "random": [
            r"Math\.random",
            r"crypto\.getRandomValues",
            r"UUID",
            r"guid",
            r"nonce",
        ],
        "timestamp": [
            r"Date\.now",
            r"new\s+Date\(\)\.getTime",
            r"performance\.now",
        ],
        "cookie": [
            r"document\.cookie",
            r"\.getCookie",
            r"Cookie\.get",
        ],
        "storage": [
            r"localStorage\.getItem",
            r"sessionStorage\.getItem",
        ],
        "response": [
            r"fetch.*\.then",
            r"\.response\.json",
            r"xhr\.response",
        ],
    }
    
    # Known taint sinks (crypto-related)
    SINK_PATTERNS = {
        "crypto": [
            r"\.sign\(",
            r"\.verify\(",
            r"\.encrypt\(",
            r"\.hmac\(",
            r"\.digest\(",
            r"CryptoJS\.",
        ],
        "network": [
            r"fetch\(",
            r"XMLHttpRequest",
            r"\.send\(",
            r"\.post\(",
        ],
        "header": [
            r"headers\.",
            r"setRequestHeader",
        ],
        "output": [
            r"return\s+",
            r"console\.log",
        ],
    }
    
    def __init__(self):
        self.sources: list[TaintSource] = []
        self.sinks: list[TaintSink] = []
        self.paths: list[TaintPath] = []
    
    def analyze(self, source_code: str) -> dict:
        """
        Perform taint analysis on source code.
        
        Returns:
            Dictionary with sources, sinks, and paths
        """
        self.sources = self._find_sources(source_code)
        self.sinks = self._find_sinks(source_code)
        self.paths = self._find_paths(source_code)
        
        return {
            "sources": [
                {"name": s.name, "type": s.type, "location": s.location, "confidence": s.confidence}
                for s in self.sources
            ],
            "sinks": [
                {"name": s.name, "type": s.type, "location": s.location, "field": s.field}
                for s in self.sinks
            ],
            "paths": [
                {
                    "source": p.source.name,
                    "sink": p.sink.name,
                    "transformations": p.transformations,
                    "confidence": p.confidence,
                }
                for p in self.paths
            ],
        }
    
    def _find_sources(self, code: str) -> list[TaintSource]:
        """Find potential taint sources"""
        sources = []
        
        for source_type, patterns in self.SOURCE_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, code, re.IGNORECASE)
                for match in matches:
                    location = f"Line ~{code[:match.start()].count(chr(10)) + 1}"
                    sources.append(TaintSource(
                        name=match.group(),
                        type=source_type,
                        location=location,
                        confidence=0.8,
                    ))
        
        return sources
    
    def _find_sinks(self, code: str) -> list[TaintSink]:
        """Find potential taint sinks"""
        sinks = []
        
        for sink_type, patterns in self.SINK_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, code, re.IGNORECASE)
                for match in matches:
                    location = f"Line ~{code[:match.start()].count(chr(10)) + 1}"
                    sinks.append(TaintSink(
                        name=match.group(),
                        type=sink_type,
                        location=location,
                    ))
        
        return sinks
    
    def _find_paths(self, code: str) -> list[TaintPath]:
        """Find potential taint paths (source to sink)"""
        paths = []
        
        # Simple heuristic: if source and sink appear in the same function
        # or within reasonable distance, consider it a path
        for source in self.sources:
            for sink in self.sinks:
                # Check if they're in the same region
                source_pos = code.find(source.name)
                sink_pos = code.find(sink.name)
                
                if source_pos >= 0 and sink_pos >= 0:
                    # Find transformations between them
                    between = code[source_pos:sink_pos]
                    transforms = self._detect_transformations(between)
                    
                    if transforms or abs(sink_pos - source_pos) < 5000:  # Within 5KB
                        paths.append(TaintPath(
                            source=source,
                            sink=sink,
                            transformations=transforms,
                            confidence=0.7,
                        ))
        
        return paths
    
    def _detect_transformations(self, code: str) -> list[str]:
        """Detect data transformations between source and sink"""
        transforms = []
        
        transform_patterns = [
            (r"\.toString\s*\(", "toString"),
            (r"\.join\s*\(", "join"),
            (r"\.concat\s*\(", "concat"),
            (r"\+", "concatenation"),
            (r"JSON\.stringify", "JSON.stringify"),
            (r"JSON\.parse", "JSON.parse"),
            (r"atob\s*\(", "base64_decode"),
            (r"btoa\s*\(", "base64_encode"),
            (r"encodeURIComponent", "url_encode"),
            (r"decodeURIComponent", "url_decode"),
            (r"Array\.from.*map", "array_map"),
            (r"\.map\s*\(", "map"),
            (r"\.filter\s*\(", "filter"),
        ]
        
        for pattern, name in transform_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                transforms.append(name)
        
        return transforms


# =============================================================================
# OBFUSCATION DETECTION
# =============================================================================

class ObfuscationDetector:
    """
    Detects code obfuscation techniques.
    """
    
    OBFUSCATION_PATTERNS = {
        "string_encoding": [
            r"\\x[0-9a-fA-F]{2}",
            r"\\u[0-9a-fA-F]{4}",
            r"String\.fromCharCode",
            r"eval\s*\(\s*",
        ],
        "variable_obfuscation": [
            r"var\s+[a-z]\s*=\s*['\"][^'\"]+['\"]",
            r"window\[[a-z]['\"]",
            r"this\[[a-z]['\"]",
        ],
        "control_flow": [
            r"case\s+\d+:",
            r"switch\s*\(",
            r"while\s*\(\s*!0\s*\)",
            r"while\s*\(\s*!1\s*\)",
        ],
        "dead_code": [
            r"if\s*\(\s*!1\s*\)",
            r"if\s*\(\s*!0\s*\)",
            r"if\s*\(\s*false\s*\)",
        ],
        "packed": [
            r"eval\s*\(\s*function\s*\(",
            r" eval\(.*\(function",
            r"\$wp\s*\(",
            r"packed",
        ],
        "minified": [
            r";\s*}\s*;",
            r"function\s*\(\s*\)\s*{\s*",
            r"var\s+\w+=\w+=\w+=",
        ],
    }
    
    def analyze(self, code: str) -> dict:
        """
        Analyze code for obfuscation techniques.
        
        Returns:
            Dictionary with detected techniques and confidence scores
        """
        results = {
            "is_obfuscated": False,
            "techniques": [],
            "entropy": 0.0,
            "recommendations": [],
        }
        
        # Check each obfuscation type
        for technique, patterns in self.OBFUSCATION_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                matches += len(re.findall(pattern, code, re.IGNORECASE))
            
            if matches > 0:
                results["techniques"].append({
                    "type": technique,
                    "confidence": min(matches * 0.2, 1.0),
                    "matches": matches,
                })
                results["is_obfuscated"] = True
        
        # Calculate entropy
        results["entropy"] = self._calculate_entropy(code)
        
        # Generate recommendations
        if results["is_obfuscated"]:
            techniques = [t["type"] for t in results["techniques"]]
            
            if "packed" in techniques:
                results["recommendations"].append("Code is packed - consider using unpacker")
            if "string_encoding" in techniques:
                results["recommendations"].append("Strings are encoded - deobfuscation may help")
            if results["entropy"] > 4.5:
                results["recommendations"].append("High entropy suggests heavy obfuscation")
        
        return results
    
    def _calculate_entropy(self, code: str) -> float:
        """Calculate Shannon entropy of the code"""
        if not code:
            return 0.0
        
        # Count character frequencies
        freq = {}
        for char in code:
            freq[char] = freq.get(char, 0) + 1
        
        # Calculate entropy
        import math
        entropy = 0.0
        length = len(code)
        
        for count in freq.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
        
        return entropy


# =============================================================================
# CODE SIMILARITY
# =============================================================================

class CodeSimilarity:
    """
    Analyze code similarity for pattern detection.
    """
    
    def calculate_hash(self, code: str, method: str = "md5") -> str:
        """Calculate hash of code"""
        if method == "md5":
            return hashlib.md5(code.encode()).hexdigest()
        elif method == "sha256":
            return hashlib.sha256(code.encode()).hexdigest()
        return ""
    
    def extract_features(self, code: str) -> dict:
        """Extract features for similarity comparison"""
        # Simple feature extraction
        features = {
            "length": len(code),
            "lines": len(code.split("\n")),
            "functions": len(re.findall(r"function\s+\w+", code)),
            "calls": len(re.findall(r"\w+\s*\(", code)),
            "strings": len(re.findall(r"['\"][^'\"]*['\"]", code)),
            "numbers": len(re.findall(r"\b\d+\b", code)),
            "hash_md5": self.calculate_hash(code, "md5"),
            "hash_sha256": self.calculate_hash(code, "sha256"),
        }
        return features
    
    def compare(self, code1: str, code2: str) -> float:
        """
        Compare two code snippets for similarity.
        
        Returns:
            Similarity score (0-1)
        """
        # Simple similarity based on common substrings
        if not code1 or not code2:
            return 0.0
        
        # Find common 3-grams
        def get_ngrams(text: str, n: int = 3) -> set:
            return set(text[i:i+n] for i in range(len(text) - n + 1))
        
        ngrams1 = get_ngrams(code1)
        ngrams2 = get_ngrams(code2)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        return intersection / union if union > 0 else 0.0


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "TaintSource",
    "TaintSink", 
    "TaintPath",
    "TaintAnalyzer",
    "ObfuscationDetector",
    "CodeSimilarity",
]
