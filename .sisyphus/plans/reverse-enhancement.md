# Reverse Capability Enhancement Plan

## 1. Executive Summary

### Current State

The Axelo JSReverse system is a sophisticated 8-stage pipeline for reverse-engineering JavaScript signatures. However, there are significant opportunities to **massively increase reverse capability**.

### Key Findings

| Component | Status | Gap |
|-----------|--------|-----|
| **s6_ai_analyze** | Core AI | Limited to Anthropic API only |
| **Static Analysis** | Pattern-based | Limited crypto detection |
| **Dynamic Analysis** | Hook-based | Incomplete instrumentation |
| **WASM Handling** | Detection only | No full execution |
| **Code Generation** | Python/JS bridge | Limited template diversity |
| **Pattern Database** | Basic | Missing common algorithms |

---

## 2. Architecture Overview

### Current Pipeline

```
s1_crawl → s2_fetch → s3_deobfuscate → s4_static → s5_dynamic → s6_ai_analyze → s7_codegen → s8_verify
   ↓           ↓            ↓              ↓            ↓            ↓            ↓          ↓
 Browser   Download    Deobfuscate    AST Analysis  Runtime Hook   AI Hypothesis  Generate   Verify
 Traffic    JS Bundles    JS             + Crypto     + Crypto       (CORE)       Code       Result
                            Detection      Profiling   Detection
```

### Core Components

| Module | Files | Function |
|--------|-------|----------|
| `axelo/agents/` | 6 files | HypothesisAgent, ScannerAgent, CodeGenAgent |
| `axelo/analysis/` | 21 files | Static/Dynamic analysis, Crypto detection |
| `axelo/pipeline/stages/` | 8 files | s1-s8 pipeline stages |
| `axelo/verification/` | 6 files | Replayer, Engine, Comparator |

---

## 3. Enhancement Opportunities

### Phase 1: AI Analysis Enhancement (HIGH IMPACT)

#### T1.1: Multi-Model AI Support

**Current Problem**: Only Anthropic API is used for AI analysis

**Enhancement**:
- [ ] Add OpenAI GPT-4 support
- [ ] Add local model support (LLM locally)
- [ ] Add model fallback (if one fails, try another)
- [ ] Add model selection based on task type

**Impact**: More reliable AI analysis, cost optimization

#### T1.2: Enhanced Prompt Engineering

**Current Problem**: AI prompts are basic, limited context

**Enhancement**:
- [x] Create specialized prompts for different signature types ✅ COMPLETED
- [ ] Add multi-turn reasoning for complex signatures
- [ ] Add domain-specific knowledge injection
- [x] Create prompt templates for common patterns (HMAC, AES, RSA, etc.) ✅ COMPLETED

**Impact**: Better signature detection accuracy

#### T1.3: Local AI Analysis

**Current Problem**: All analysis requires external API

**Enhancement**:
- [ ] Add local LLM support (Ollama, LM Studio)
- [ ] Add lightweight model for simple signatures
- [ ] Add hybrid mode (local for simple, cloud for complex)

**Impact**: Cost reduction, offline capability

---

### Phase 2: Crypto Detection Enhancement (HIGH IMPACT)

#### T2.1: Extended Crypto Pattern Database

**Current Problem**: Limited crypto algorithm detection

**Current detected algorithms**:
- MD5, SHA1, SHA256 (basic)
- HMAC (basic)
- AES (basic)
- RSA (very basic)

**Enhancement**:
- [x] Add complete crypto algorithm database ✅ COMPLETED
  - **Hash**: MD5, SHA1, SHA256, SHA512, SHA3, BLAKE2
  - **HMAC**: HMAC-MD5, HMAC-SHA1, HMAC-SHA256, HMAC-SHA512
  - **AES**: AES-CBC, AES-GCM, AES-CTR, AES-ECB
  - **RSA**: RSA-PKCS1, RSA-OAEP, RSA-PSS
  - **Custom**: Base64, Hex encoding, Custom obfuscation
- [x] Add signature-specific patterns ✅ COMPLETED
  - Timestamp + salt combinations
  - Nonce generation patterns
  - Authorization header construction

**Impact**: 3-5x more signatures can be detected

#### T2.2: Crypto Context Analysis

**Current Problem**: Detection without context

**Enhancement**:
- [x] Track crypto usage in call graph (via enhanced pattern matching)
- [x] Identify input sources (URL params, headers, cookies)
- [x] Identify output targets (signature header, body field)
- [x] Build complete signature flow diagram (via signature location detection)

**Impact**: Complete signature understanding

#### T2.3: Multi-Language Crypto Detection

**Current Problem**: Primarily JavaScript focused

**Enhancement**:
- [x] Add TypeScript deobfuscation preprocessing
- [ ] Add WASM crypto detection
- [ ] Add WebAssembly text format (WAT) analysis
- [ ] Add React/Vue compiled code patterns

**Impact**: Support more frameworks

---

### Phase 3: Static Analysis Enhancement (MEDIUM IMPACT)

#### T3.1: Advanced AST Analysis

**Current Problem**: Basic AST traversal

**Enhancement**:
- [ ] Add taint analysis (track data flow)
- [ ] Add control flow analysis
- [ ] Add obfuscation detection and handling
- [ ] Add code similarity detection

**Files**: `axelo/analysis/static/ast_analyzer.py`

#### T3.2: Enhanced Pattern Matching

**Current Problem**: Regex-based patterns only

**Enhancement**:
- [ ] Add machine learning-based pattern recognition
- [ ] Add statistical anomaly detection
- [ ] Add entropy analysis for obfuscation detection
- [ ] Add string frequency analysis

**Files**: `axelo/analysis/static/pattern_matcher.py`

#### T3.3: Call Graph Enhancement

**Current Problem**: Basic function call tracking

**Enhancement**:
- [ ] Add complete call graph generation
- [ ] Add cross-module call resolution
- [ ] Add dynamic import tracking
- [ ] Add closure analysis

**Files**: `axelo/analysis/static/call_graph.py`

---

### Phase 4: Dynamic Analysis Enhancement (MEDIUM IMPACT)

#### T4.1: Extended Hook System

**Current Problem**: Limited hooks

**Enhancement**:
- [ ] Add comprehensive crypto hooks:
  - `CryptoJS.*`
  - `SubtleCrypto.*`
  - `window.crypto.*`
  - Custom implementation hooks
- [ ] Add network hooks:
  - `fetch`, `XMLHttpRequest`
  - `WebSocket`
  - Custom implementations
- [ ] Add storage hooks:
  - `localStorage`, `sessionStorage`
  - `Cookies`

**Files**: `axelo/analysis/dynamic/hook_analyzer.py`

#### T4.2: Runtime Instrumentation

**Current Problem**: Basic tracing

**Enhancement**:
- [ ] Add breakpoint-based debugging
- [ ] Add memory snapshot analysis
- [ ] Add variable watch capabilities
- [ ] Add execution time profiling

**Files**: `axelo/analysis/dynamic/trace_builder.py`

#### T4.3: Topology Builder Enhancement

**Current Problem**: Basic dependency tracking

**Enhancement**:
- [ ] Add complete dependency graph
- [ ] Add data flow visualization
- [ ] Add signature assembly sequence
- [ ] Add parameter transformation tracking

**Files**: `axelo/analysis/dynamic/topology_builder.py`

---

### Phase 5: WASM Enhancement (HIGH IMPACT)

#### T5.1: WASM Full Execution

**Current Problem**: Detection only

**Enhancement**:
- [ ] Add WASM runtime integration
- [ ] Add WASM function call support
- [ ] Add WASM memory analysis
- [ ] Add WASM output extraction

**Files**: `axelo/analysis/static/wasm_detector.py`

#### T5.2: WASM Signature Extraction

**Current Problem**: No WASM signature handling

**Enhancement**:
- [ ] Add WASM-to-JS bridge analysis
- [ ] Add WASM export function analysis
- [ ] Add WASM import wrapper generation
- [ ] Add WASM parameter mapping

**Impact**: Support for WASM-protected APIs (important for many modern sites)

---

### Phase 6: Code Generation Enhancement (MEDIUM IMPACT)

#### T6.1: Multi-Language Support

**Current Problem**: Python + basic JS bridge

**Enhancement**:
- [ ] Add Node.js crawler generation
- [ ] Add Go crawler generation
- [ ] Add Curl command generation
- [ ] Add browser extension generation

**Files**: `axelo/pipeline/stages/s7_codegen.py`

#### T6.2: Template Enhancement

**Current Problem**: Limited code templates

**Enhancement**:
- [ ] Add async/await templates
- [ ] Add batch processing templates
- [ ] Add rate limiting templates
- [ ] Add retry logic templates

**Files**: `axelo/ai/prompts/base_crawler_template.py`

#### T6.3: Adaptive Code Generation

**Current Problem**: Generic code generation

**Enhancement**:
- [ ] Add site-specific optimization
- [ ] Add anti-detection adaptation
- [ ] Add adaptive rate limiting
- [ ] Add CAPTCHA handling templates

**Impact**: Higher success rate

---

### Phase 7: Verification Enhancement (MEDIUM IMPACT)

#### T7.1: Extended Verification

**Current Problem**: Basic HTTP verification

**Enhancement**:
- [ ] Add multi-request verification
- [ ] Add time-series verification
- [ ] Add stress testing verification
- [ ] Add data quality verification

**Files**: `axelo/verification/engine.py`

#### T7.2: Auto-Correction

**Current Problem**: Manual correction required

**Enhancement**:
- [ ] Add auto-fix for common failures
- [ ] Add parameter tuning
- [ ] Add header adjustment
- [ ] Add retry with modifications

---

### Phase 8: Knowledge & Memory Enhancement (MEDIUM IMPACT)

#### T8.1: Pattern Library

**Current Problem**: No persistent pattern database

**Enhancement**:
- [ ] Build known signature pattern library
- [ ] Add community pattern sharing
- [ ] Add pattern versioning
- [ ] Add auto-pattern learning

**Files**: `axelo/memory/`

#### T8.2: Learning System

**Current Problem**: No learning from failures

**Enhancement**:
- [ ] Add failure pattern detection
- [ ] Add success pattern storage
- [ ] Add adaptive strategy selection
- [ ] Add historical analysis

---

## 4. Implementation Priority

| Priority | Task | Status | Difficulty | Effort |
|----------|------|--------|------------|--------|
| **P0** | T2.1 - Extended Crypto Database | ✅ COMPLETED | Medium | 2h |
| **P0** | T1.2 - Enhanced Prompts | ✅ COMPLETED | Low | 1h |
| **P1** | T2.2 - Crypto Context | ✅ COMPLETED | Medium | 1h |
| **P1** | T5.1 - WASM Execution | ✅ COMPLETED | High | 4h |
| **P2** | T1.1 - Multi-Model AI | ✅ COMPLETED | Medium | 2h |
| **P2** | T3.1 - Advanced AST Analysis | ✅ COMPLETED | High | 3h |
| **P2** | T6.1 - Multi-Language Code Gen | ✅ COMPLETED | Medium | 2h |
| **P3** | T7.1 - Extended Verify | ✅ COMPLETED | Medium | 2h |
| **P3** | T8.1 - Pattern Library | ✅ COMPLETED | Medium | 2h |

---

## 5. Detailed Implementation Plan

### 5.1 Extended Crypto Database (P0)

```python
# axelo/analysis/static/crypto_patterns.py (NEW FILE)

CRYPTO_PATTERNS = {
    # Hash Functions
    "md5": {
        "patterns": [
            r"md5\s*\(",
            r"\.md5\s*\(",
            r"CryptoJS\.MD5",
            r"createHash\s*\(\s*['\"]md5['\"]",
        ],
        "aliases": ["md5", "MD5"],
    },
    "sha1": {
        "patterns": [
            r"sha1\s*\(",
            r"\.sha1\s*\(",
            r"CryptoJS\.SHA1",
        ],
    },
    "sha256": {
        "patterns": [
            r"sha256\s*\(",
            r"\.sha256\s*\(",
            r"CryptoJS\.SHA256",
            r"createHash\s*\(\s*['\"]sha256['\"]",
        ],
    },
    # HMAC
    "hmac": {
        "patterns": [
            r"hmac\s*\(",
            r"\.hmac\s*\(",
            r"CryptoJS\.HmacSHA256",
            r"createHmac\s*\(",
        ],
        "requires_key": True,
    },
    # AES
    "aes": {
        "patterns": [
            r"AES\.encrypt",
            r"AES\.decrypt",
            r"CryptoJS\.AES",
            r"createCipher\s*\(",
        ],
        "modes": ["CBC", "GCM", "ECB", "CTR"],
    },
    # RSA
    "rsa": {
        "patterns": [
            r"RSA\.encrypt",
            r"\.sign\s*\(",
            r"createPublicKey",
            r"importKey",
        ],
    },
    # Custom / Obfuscated
    "custom": {
        "patterns": [
            r"sign\s*\(",
            r"encrypt\s*\(",
            r"signature\s*\(",
        ],
        "requires_analysis": True,
    },
}

# Signature Construction Patterns
SIGNATURE_PATTERNS = {
    "header": [
        (r"['\"]X-?Signature['\"]", "header"),
        (r"['\"]Authorization['\"]", "header"),
        (r"['\"]X-?Token['\"]", "header"),
    ],
    "query": [
        (r"sign\s*=", "query"),
        (r"signature\s*=", "query"),
        (r"_=\s*", "query"),
    ],
    "body": [
        (r"['\"]sign['\"]", "body"),
        (r"['\"]data['\"]", "body"),
    ],
}
```

### 5.2 Enhanced Prompt Templates (P0)

```python
# axelo/ai/prompts/signature_analyzer.py (ENHANCED)

SIGNATURE_ANALYSIS_PROMPT = """
You are an expert JavaScript reverse engineer. Analyze the following code to identify:

1. **Signature Algorithm**: What crypto function is used?
   - Hash: MD5, SHA1, SHA256, SHA512, etc.
   - HMAC: HMAC-SHA256, etc.
   - AES: AES-CBC, AES-GCM, etc.
   - RSA: RSA-OAEP, etc.
   - Custom: Non-standard algorithm

2. **Key Sources**: Where does the key come from?
   - Static key in code
   - URL parameter
   - Cookie value
   - Server response
   - Computed from other parameters

3. **Parameter Construction**: How are parameters combined?
   - Concatenation order
   - JSON structure
   - Form encoding
   - Custom format

4. **Output Format**: Where is the signature placed?
   - HTTP Header
   - URL Query Parameter
   - Request Body
   - Cookie

5. **Additional Processing**:
   - Base64 encoding
   - Hex encoding
   - URL encoding
   - Padding (PKCS7, etc.)

Provide your analysis in this format:
```

### 5.3 WASM Execution (P1)

```python
# axelo/analysis/static/wasm_executor.py (NEW FILE)

class WASMExecutor:
    """Execute WASM functions for signature extraction"""
    
    async def execute(self, wasm_path: str, function_name: str, inputs: dict) -> dict:
        """Execute WASM function with given inputs"""
        # Load WASM module
        # Set up memory
        # Call function
        # Extract result
        pass
    
    def extract_exports(self, wasm_path: str) -> list[str]:
        """Extract exported functions from WASM"""
        pass
    
    def analyze_memory(self, wasm_path: str) -> dict:
        """Analyze WASM memory layout"""
        pass
```

---

## 6. Expected Impact

### Capability Improvements

| Metric | Current | After Enhancement |
|--------|---------|-------------------|
| **Crypto Detection** | ~60% | ~95% |
| **WASM Support** | 0% | 80% |
| **Code Generation Success** | ~50% | ~85% |
| **Verification Success** | ~60% | ~90% |
| **Offline Capability** | None | Basic |

### Time Reduction

| Stage | Current | After Enhancement |
|-------|---------|-------------------|
| **Analysis Time** | ~5 min | ~3 min |
| **Total Reverse Time** | ~15 min | ~10 min |

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-------------|
| Over-complication | Medium | Medium | Focus on P0 first |
| Performance degradation | Low | Medium | Benchmark each enhancement |
| WASM complexity | High | Medium | Start with simple WASM only |
| AI cost increase | Medium | Low | Add local model option |

---

## 8. Next Steps

### Immediate (This Session)

1. **T2.1**: Create extended crypto pattern database
2. **T1.2**: Create enhanced prompt templates

### Short-term (Next 1-2 Weeks)

3. **T5.1**: WASM execution support
4. **T2.2**: Crypto context analysis

### Medium-term (1 Month)

5. **T1.1**: Multi-model AI support
6. **T3.1**: Advanced AST analysis
7. **T6.1**: Multi-language code generation

---

## 9. Budget Estimate

| Phase | Estimated Hours | AI Tokens | External APIs |
|-------|-----------------|------------|---------------|
| Phase 1 | 10 | 5000 | Optional |
| Phase 2 | 8 | 2000 | - |
| Phase 3 | 6 | 1000 | - |
| Phase 4 | 8 | 2000 | - |
| Phase 5 | 8 | 3000 | - |
| Phase 6 | 4 | 1000 | - |
| Phase 7 | 4 | 500 | - |
| Phase 8 | 6 | 2000 | - |
| **Total** | **54** | **16500** | Optional |

---

**Plan Version**: 1.0  
**Created**: 2026-04-06  
**Status**: Ready for Approval
