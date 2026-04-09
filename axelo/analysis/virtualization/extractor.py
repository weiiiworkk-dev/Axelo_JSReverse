"""
VM bytecode extractor.

Given a :class:`VMDetectionResult` and the raw JS source, this module
attempts to pull out three artefacts that are needed to replicate or
decompile the custom VM:

1. ``raw_bytecode``    — the integer opcode sequence
2. ``constant_pool``   — the string / numeric constants referenced by index
3. ``handler_map``     — a mapping of opcode integer → handler source snippet

All extraction is done with regex on the source text plus an optional call
to the existing :class:`NodeRunner` if more precise AST traversal is needed.
If extraction fails (sparse or dynamic bytecode), the extractor returns None
gracefully so the pipeline can continue without crashing.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from axelo.analysis.virtualization.detector import VMDetectionResult

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# 用于从字符串数组中精确提取带引号字符串（支持内部逗号和转义字符）
_QUOTED_STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')

_NUMERIC_ARRAY_RE = re.compile(
    r"(?:var|let|const)\s+([\w$]+)\s*=\s*\[\s*"
    r"((?:0x[0-9a-fA-F]+|\d+)(?:\s*,\s*(?:0x[0-9a-fA-F]+|\d+))*)\s*\]"
)

_STRING_ARRAY_RE = re.compile(
    r"(?:var|let|const)\s+([\w$]+)\s*=\s*\[\s*"
    r"((?:\"[^\"]*\"|'[^']*')(?:\s*,\s*(?:\"[^\"]*\"|'[^']*'))*)\s*\]"
)

_SWITCH_CASE_RE = re.compile(
    r"case\s+(0x[0-9a-fA-F]+|\d+)\s*:(.*?)(?=case\s+(?:0x[0-9a-fA-F]+|\d+)\s*:|default\s*:|^\s*\})",
    re.S | re.M,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class BytecodeExtract(BaseModel):
    raw_bytecode: list[int] = Field(default_factory=list)
    constant_pool: list[str] = Field(default_factory=list)
    handler_map: dict[str, str] = Field(default_factory=dict)   # str(opcode) → handler snippet
    vm_function_name: str = ""
    bytecode_var_name: str = ""
    estimated_instruction_count: int = 0

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

_MAX_HANDLER_SNIPPET_LEN = 400


class BytecodeExtractor:
    """
    Extract bytecode and handler information from VM-obfuscated JS.

    Usage::

        extractor = BytecodeExtractor()
        result = extractor.extract(source, detection)
        if result:
            print(result.raw_bytecode[:20])
    """

    def extract(
        self,
        source: str,
        detection: VMDetectionResult,
        node_runner=None,          # optional: axelo.js_tools.runner.NodeRunner
    ) -> BytecodeExtract | None:
        """
        Try all extraction strategies in order of reliability.

        Returns a :class:`BytecodeExtract` on success, or *None* if no
        meaningful data could be pulled out.
        """
        try:
            return self._extract_regex(source, detection)
        except Exception as exc:
            log.warning("vm_extract_regex_failed", error=str(exc))

        if node_runner is not None:
            try:
                return self._extract_via_node(source, detection, node_runner)
            except Exception as exc:
                log.warning("vm_extract_node_failed", error=str(exc))

        return None

    # ------------------------------------------------------------------
    # Strategy A: pure-regex extraction (fast, no Node.js)
    # ------------------------------------------------------------------

    def _extract_regex(self, source: str, detection: VMDetectionResult) -> BytecodeExtract | None:
        raw_bytecode:  list[int] = []
        constant_pool: list[str] = []
        handler_map:   dict[str, str] = {}
        bc_var_name    = ""
        vm_func_name   = detection.dispatch_func_candidates[0] if detection.dispatch_func_candidates else ""

        # 1. Extract numeric arrays (bytecode candidates)
        best_len = 0
        for m in _NUMERIC_ARRAY_RE.finditer(source):
            var_name  = m.group(1)
            raw_items = m.group(2).split(",")
            try:
                values = [int(v.strip(), 0) for v in raw_items if v.strip()]
            except ValueError:
                continue
            if len(values) > best_len:
                best_len     = len(values)
                raw_bytecode = values
                bc_var_name  = var_name

        # 2. Extract string constant pools（用 _QUOTED_STR_RE 精确提取，避免含逗号字符串被截断）
        for m in _STRING_ARRAY_RE.finditer(source):
            raw_content = m.group(0)
            quoted_strings = _QUOTED_STR_RE.findall(raw_content)
            pool = [s[1:-1] for s in quoted_strings]  # 去掉外层引号
            if len(pool) > len(constant_pool):
                constant_pool = pool

        # 3. Extract case handlers from the largest switch block
        switch_blocks = list(re.finditer(
            r"switch\s*\([^)]{0,80}\)\s*\{(?:[^{}]|\{[^{}]*\}){1,5000}?\}",
            source,
            re.S,
        ))
        if switch_blocks:
            # Pick the block with the most case labels
            best_block = max(switch_blocks, key=lambda m: m.group(0).count("case "))
            block_text = best_block.group(0)
            for m in _SWITCH_CASE_RE.finditer(block_text):
                opcode  = str(int(m.group(1).strip(), 0))
                snippet = m.group(2).strip()[:_MAX_HANDLER_SNIPPET_LEN]
                handler_map[opcode] = snippet

        if not raw_bytecode and not handler_map:
            return None

        return BytecodeExtract(
            raw_bytecode=raw_bytecode,
            constant_pool=constant_pool,
            handler_map=handler_map,
            vm_function_name=vm_func_name,
            bytecode_var_name=bc_var_name,
            estimated_instruction_count=len(raw_bytecode),
        )

    # ------------------------------------------------------------------
    # Strategy B: Node.js-assisted extraction (more accurate AST traversal)
    # ------------------------------------------------------------------

    _NODE_EXTRACT_SCRIPT = r"""
const babelParser = require('@babel/parser');
const babelTraverse = require('@babel/traverse').default;

const src = process.argv[2];
const code = require('fs').readFileSync(src, 'utf8');

let largestNumericArray = null;
let largestNumericName  = '';
let largestStringArray  = null;
let handlerMap = {};

const ast = babelParser.parse(code, { errorRecovery: true });

babelTraverse(ast, {
    VariableDeclarator(path) {
        const init = path.node.init;
        if (!init || init.type !== 'ArrayExpression') return;
        const elements = init.elements || [];
        const nums = elements.filter(e => e && e.type === 'NumericLiteral');
        const strs = elements.filter(e => e && e.type === 'StringLiteral');
        if (nums.length >= 50 && nums.length > (largestNumericArray ? largestNumericArray.length : 0)) {
            largestNumericArray = nums.map(e => e.value);
            largestNumericName  = path.node.id && path.node.id.name ? path.node.id.name : '';
        }
        if (strs.length >= 5 && strs.length > (largestStringArray ? largestStringArray.length : 0)) {
            largestStringArray = strs.map(e => e.value);
        }
    },
    SwitchStatement(path) {
        const cases = path.node.cases || [];
        if (cases.length < 8) return;
        cases.forEach(c => {
            if (!c.test) return;
            const key = c.test.value !== undefined ? String(c.test.value) : null;
            if (key === null) return;
            const body = c.consequent.map(s => s.type).join(';');
            if (!handlerMap[key]) handlerMap[key] = body;
        });
    }
});

console.log(JSON.stringify({
    bytecode: largestNumericArray || [],
    bytecodeVar: largestNumericName,
    constantPool: largestStringArray || [],
    handlerMap: handlerMap
}));
"""

    def _extract_via_node(
        self,
        source: str,
        detection: VMDetectionResult,
        node_runner,
    ) -> BytecodeExtract | None:
        # Write source to a temp file and run the extraction script.
        # Both source and script get unique temp filenames to avoid concurrent-worker collisions.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", encoding="utf-8", delete=False
        ) as src_fh:
            src_fh.write(source)
            src_path = src_fh.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_vm_extract.js", encoding="utf-8",
            delete=False, dir=str(node_runner.scripts_dir),
        ) as script_fh:
            script_fh.write(self._NODE_EXTRACT_SCRIPT)
            script_path = script_fh.name

        try:
            proc = subprocess.run(
                [node_runner.node_bin, script_path, src_path],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(node_runner.scripts_dir),
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return None
            data = json.loads(proc.stdout.strip())
        except Exception:
            return None
        finally:
            Path(src_path).unlink(missing_ok=True)
            Path(script_path).unlink(missing_ok=True)

        raw_bc      = [int(v) for v in data.get("bytecode", [])]
        pool        = [str(v) for v in data.get("constantPool", [])]
        bc_var      = data.get("bytecodeVar", "")
        handler_map = {str(k): str(v) for k, v in data.get("handlerMap", {}).items()}

        if not raw_bc and not pool:
            return None

        return BytecodeExtract(
            raw_bytecode=raw_bc,
            constant_pool=pool,
            handler_map=handler_map,
            vm_function_name=detection.dispatch_func_candidates[0]
                if detection.dispatch_func_candidates else "",
            bytecode_var_name=bc_var,
            estimated_instruction_count=len(raw_bc),
        )
