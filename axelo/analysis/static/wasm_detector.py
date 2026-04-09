"""
Static WASM usage detector.

Scans JS source text for WebAssembly loading patterns. When detected in S4,
a warning is logged so the operator knows to enable the bridge (S5 dynamic)
for full WASM analysis. This complements the runtime-only WASM API in
axelo/browser/bridge_client.py.

Enhanced with:
- Export function detection
- WASM signature indicators
- More comprehensive pattern matching
"""
from __future__ import annotations

import re
from typing import Any

# Patterns that indicate the JS source loads or compiles WASM modules
_WASM_STATIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'WebAssembly\.instantiate', re.I),
    re.compile(r'WebAssembly\.compile', re.I),
    re.compile(r'WebAssembly\.instantiateStreaming', re.I),
    re.compile(r'new\s+WebAssembly\.Module', re.I),
    re.compile(r'new\s+WebAssembly\.Instance', re.I),
    re.compile(r'fetch\s*\([^)]*\.wasm', re.I),
    re.compile(r'["\']([^"\']*\.wasm)["\']', re.I),
]

# Patterns that indicate WASM might be used for signatures/encryption
_WASM_SIGNATURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'\.sign\s*\(', re.I),
    re.compile(r'\.verify\s*\(', re.I),
    re.compile(r'\.digest\s*\(', re.I),
    re.compile(r'\.encrypt\s*\(', re.I),
    re.compile(r'\.decrypt\s*\(', re.I),
    re.compile(r'md5|sha[12356]|hmac|aes', re.I),
    # Common WASM crypto wrapper patterns
    re.compile(r'wasm.*crypto', re.I),
    re.compile(r'crypto.*wasm', re.I),
    re.compile(r'\.wasm\s*\.\s*\w+\s*\(', re.I),  # WASM module export calls
]

# Common WASM export function name patterns
_WASM_EXPORT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'(?:export|function)\s*["\']?(\w*(?:sign|verify|hash|encrypt|decrypt|crypto|encode|decode)\w*)["\']?', re.I),
    re.compile(r'_sign$|_verify$|_hash$|_encrypt$', re.I),
]


def detect_wasm_usage(source: str) -> bool:
    """Return True if *source* contains WebAssembly loading patterns.

    This is a fast, purely-static check — no Node.js required.
    A True result means the bundle almost certainly loads a WASM module
    at runtime; the operator should ensure the bridge is active during S5
    so that ``list_wasm_modules()`` and ``invoke_wasm_export()`` can be used.
    """
    return any(p.search(source) for p in _WASM_STATIC_PATTERNS)


def detect_wasm_signature_usage(source: str) -> bool:
    """Return True if *source* appears to use WASM for cryptographic operations.

    This detects patterns suggesting WASM modules are used for signing,
    encryption, or hashing — valuable signal for signature extraction.
    """
    # First check if WASM is used at all
    if not detect_wasm_usage(source):
        return False
    
    # Then check for signature-related patterns
    return any(p.search(source) for p in _WASM_SIGNATURE_PATTERNS)


def extract_wasm_export_candidates(source: str) -> list[dict[str, Any]]:
    """Extract potential WASM export function names from source code.

    Args:
        source: JavaScript source code

    Returns:
        List of dictionaries with 'name' and 'context' for each candidate
    """
    candidates = []
    
    for pattern in _WASM_EXPORT_PATTERNS:
        matches = pattern.finditer(source)
        for match in matches:
            if match.groups():
                name = match.group(1) if match.lastindex else match.group(0)
                # Get surrounding context (50 chars before and after)
                start = max(0, match.start() - 30)
                end = min(len(source), match.end() + 30)
                context = source[start:end].replace('\n', ' ').strip()
                
                candidates.append({
                    "name": name.strip(),
                    "context": context,
                    "pattern_matched": pattern.pattern,
                })
    
    # Deduplicate by name
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique_candidates.append(c)
    
    return unique_candidates


def analyze_wasm_complexity(source: str) -> dict[str, Any]:
    """Analyze WASM usage complexity for strategy determination.

    Args:
        source: JavaScript source code

    Returns:
        Dictionary with complexity analysis results
    """
    has_wasm = detect_wasm_usage(source)
    has_signature = detect_wasm_signature_usage(source)
    export_candidates = extract_wasm_export_candidates(source) if has_wasm else []
    
    # Estimate complexity
    complexity = "none"
    recommended_strategy = "python_reconstruct"
    
    if has_wasm and has_signature:
        complexity = "high"
        recommended_strategy = "js_bridge"
    elif has_wasm:
        complexity = "medium"
        recommended_strategy = "js_bridge"
    
    return {
        "uses_wasm": has_wasm,
        "uses_wasm_for_signing": has_signature,
        "complexity": complexity,
        "recommended_strategy": recommended_strategy,
        "export_candidates": export_candidates[:5],  # Limit to top 5
        "needs_runtime_analysis": has_signature,
    }
