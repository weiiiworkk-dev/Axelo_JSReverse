"""
VM / virtualization-obfuscation detector.

Scans JavaScript source for three canonical VM fingerprints:

1. Dispatch loop   — while(true){ switch(vm.pc){…} } or
                     for(;;){ var op = bytecode[pc++]; switch(op){…} }
2. Opcode table    — a large array of 10+ function references used as a
                     handler dispatch table
3. Bytecode array  — a numeric array of 50+ integer / hex values that is
                     indexed throughout the file (VM bytecode constants)

Each fingerprint raises confidence by a fixed amount.  When combined with
AST-level confirmation (number of switch-case branches, element types) the
result confidence can reach 1.0.

All detection is done with regex on the *source text* — no Node.js required.
"""
from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Pattern 1 — dispatch loops
_DISPATCH_LOOP_PATTERNS: list[re.Pattern[str]] = [
    # while (true) { switch (…) {
    re.compile(r"while\s*\(\s*(?:true|1)\s*\)\s*\{[^}]{0,200}switch\s*\(", re.S),
    # for (;;) { … switch (someArr[pc++]) {
    re.compile(r"for\s*\(\s*;;\s*\)\s*\{[^}]{0,300}switch\s*\(\s*\w+\s*\[", re.S),
    # for (…) { … switch (opcodeVar) {
    re.compile(r"for\s*\([^)]{0,80}\)\s*\{[^}]{0,200}switch\s*\(\s*\w+\s*\)", re.S),
]

# Pattern 2 — opcode / handler tables
# Large array-literal with ≥10 comma-separated function references
_OPCODE_TABLE_PATTERN = re.compile(
    r"=\s*\[\s*(?:function\s*\([^)]*\)\s*\{[^}]{0,200}\}|[\w$]+)\s*"
    r"(?:,\s*(?:function\s*\([^)]*\)\s*\{[^}]{0,200}\}|[\w$]+)\s*){9,}\]",
    re.S,
)

# Pattern 3 — bytecode arrays (50+ numeric / hex values)
_BYTECODE_ARRAY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"=\s*\[\s*(?:0x[0-9a-fA-F]+\s*,\s*){49,}0x[0-9a-fA-F]+"),
    re.compile(r"=\s*\[\s*(?:\d+\s*,\s*){49,}\d+"),
]

# Heuristic: dense switch-case (≥8 numeric case labels in one switch block)
_DENSE_SWITCH_PATTERN = re.compile(
    r"switch\s*\([^)]{0,80}\)\s*\{(?:[^{}]|\{[^{}]*\}){0,3000}?\}",
    re.S,
)
_CASE_LABEL_PATTERN = re.compile(r"\bcase\s+(?:\d+|0x[0-9a-fA-F]+)\s*:")

# Variable name extraction from an array assignment:  var _X = [ … ]
_ARRAY_VAR_PATTERN = re.compile(r"(?:var|let|const)\s+([\w$]+)\s*=\s*\[")

# Function name around a switch:  function _X(...){ ... switch(...){ ... } }
_FUNC_AROUND_SWITCH = re.compile(
    r"function\s+([\w$]+)\s*\([^)]*\)\s*\{(?:[^{}]|\{[^{}]*\}){0,400}"
    r"switch\s*\([^)]{0,80}\)\s*\{",
    re.S,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class VMDetectionResult(BaseModel):
    detected: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    pattern_types: list[str] = Field(default_factory=list)
    bytecode_array_candidates: list[str] = Field(default_factory=list)
    dispatch_func_candidates: list[str] = Field(default_factory=list)
    dense_switch_count: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class VirtualizationDetector:
    """
    Stateless detector — call detect() with the JS source text.

    Optionally pass pre-parsed ``ast_data`` (dict from ASTAnalyzer) to
    improve precision, but the regex scan alone is sufficient for detection.
    """

    # Confidence increments per fingerprint
    _DISPATCH_CONFIDENCE   = 0.40
    _OPCODE_TABLE_CONFIDENCE = 0.30
    _BYTECODE_CONFIDENCE   = 0.30
    _DENSE_SWITCH_PER_BLOCK = 0.10   # per block with ≥8 cases

    def detect(
        self,
        source: str,
        ast_data: dict | None = None,
    ) -> VMDetectionResult:
        """
        Run the VM detection scan on *source*.

        Returns a :class:`VMDetectionResult` with *detected=True* and
        *confidence ≥ 0.4* if at least one strong VM fingerprint is found.
        """
        confidence    = 0.0
        pattern_types: list[str] = []
        bc_candidates: list[str] = []
        dispatch_candidates: list[str] = []
        dense_count   = 0

        # --- Pass 1: Dispatch loop ---
        for pat in _DISPATCH_LOOP_PATTERNS:
            if pat.search(source):
                confidence  += self._DISPATCH_CONFIDENCE
                pattern_types.append("dispatch_loop")

                # Extract function name(s) around the switch
                for m in _FUNC_AROUND_SWITCH.finditer(source):
                    name = m.group(1)
                    if name not in dispatch_candidates:
                        dispatch_candidates.append(name)
                break  # one increment per category

        # --- Pass 2: Opcode table ---
        if _OPCODE_TABLE_PATTERN.search(source):
            confidence   += self._OPCODE_TABLE_CONFIDENCE
            pattern_types.append("opcode_table")

        # --- Pass 3: Bytecode array ---
        for pat in _BYTECODE_ARRAY_PATTERNS:
            if pat.search(source):
                confidence += self._BYTECODE_CONFIDENCE
                pattern_types.append("bytecode_array")
                # Collect variable names of large numeric arrays
                for m in _ARRAY_VAR_PATTERN.finditer(source):
                    name = m.group(1)
                    if name not in bc_candidates:
                        bc_candidates.append(name)
                break

        # --- Pass 4: Dense switch blocks (bonus confidence, total capped at 0.20) ---
        dense_contribution = 0.0
        for block_m in _DENSE_SWITCH_PATTERN.finditer(source):
            block_text = block_m.group(0)
            case_count = len(_CASE_LABEL_PATTERN.findall(block_text))
            if case_count >= 8:
                dense_count += 1
                dense_contribution += self._DENSE_SWITCH_PER_BLOCK
        confidence += min(dense_contribution, 0.20)   # 总量上限 0.20，防止多 switch 块无限累加

        confidence = min(confidence, 1.0)
        detected   = confidence >= 0.40

        result = VMDetectionResult(
            detected=detected,
            confidence=round(confidence, 3),
            pattern_types=list(dict.fromkeys(pattern_types)),   # deduplicate, preserve order
            bytecode_array_candidates=bc_candidates[:10],
            dispatch_func_candidates=dispatch_candidates[:10],
            dense_switch_count=dense_count,
            notes=(
                f"Detected {len(pattern_types)} pattern type(s); "
                f"{dense_count} dense switch block(s)."
                if detected else "No VM fingerprints found."
            ),
        )

        if detected:
            log.debug(
                "vm_pattern_detected",
                confidence=result.confidence,
                patterns=result.pattern_types,
                dense_switches=dense_count,
            )

        return result
