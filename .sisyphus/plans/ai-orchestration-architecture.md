# AI-Centered Tool Orchestration Architecture
## Task Plan for Axelo JS Reverse Engineering System

---

## 1. Executive Summary

This document outlines a comprehensive task plan to transform the Axelo system into an **AI-centered tool orchestration platform** for automated JavaScript reverse engineering and web crawling.

**Core Vision**: The AI acts as the central orchestrator that:
1. Analyzes target websites dynamically
2. Selects and chains appropriate tools based on context
3. Extracts signature algorithms from obfuscated JavaScript
4. Generates working crawler code automatically

**Current State**: System has basic tool chain (browser → static → ai_analyze → codegen → verify) but suffers from:
- Missing integration between components
- Weak AI fallback heuristics
- No dynamic tool selection
- Separate verification systems not unified

**Target State**: Unified AI orchestration with:
- Dynamic tool selection based on site characteristics
- Real-time signature extraction and verification
- Self-improving tool chains
- End-to-end automated execution

---

## 2. Architecture Overview

### 2.1 Current Architecture (As-Is)

```
User Input
    │
    ▼
┌─────────────────────┐
│   Router/Planner    │ ← AI decides tool sequence
│   (router.py)       │
└─────────────────────┘
    │
    ▼ Sequential Tool Chain
browser → fetch_js_bundles → static → ai_analyze → codegen → verify
    │                         │              │            │
    ▼                         ▼              ▼            ▼
Browser Context         JS Bundles      Hypothesis    Python Code
```

**Issues Identified**:
- Linear tool chain, no branching based on site complexity
- Tool outputs not fully integrated (SignatureExtractor not in chain)
- AI fallback produces weak hypotheses
- Verify tool and VerificationEngine operate independently

### 2.2 Target Architecture (To-Be)

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Orchestration Layer                       │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │  Intent       │  │  Tool         │  │  Context      │       │
│  │  Classifier   │→ │  Selector    │→ │  Manager      │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│         │                  │                   │                │
│         ▼                  ▼                   ▼                │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Tool Executor (Async)                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ Browser │          │ Static  │          │  AI     │
   │ Tool    │          │ Analysis│          │ Analyze │
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ Extract │          │ Crypto  │          │Hypothesis│
   │ Signature│          │ Detect  │          │ Generator│
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Code Gen +    │
                    │  Verification  │
                    └─────────────────┘
```

### 2.3 Key Components

| Component | Responsibility | Current State |
|-----------|---------------|---------------|
| **Intent Classifier** | Analyze user request, determine goal | Basic (router.py) |
| **Tool Selector** | Dynamically choose best tools | Static (_select_tools) |
| **Context Manager** | Maintain execution state across tools | Partial (ToolState) |
| **Signature Extractor** | Extract keys from JS | Implemented, not integrated |
| **Dynamic Analyzer** | Execute JS in browser context | Implemented, not integrated |
| **Hypothesis Generator** | Generate signing algorithm hypotheses | Basic (ai_tool.py) |
| **Code Generator** | Produce working crawler code | Working (codegen_tool.py) |
| **Verification Engine** | Test generated code | Split (verify_tool + engine) |

---

## 3. Detailed Task Breakdown

### Phase 1: Foundation (Week 1-2)

#### Task 1.1: Unified Tool Registry and Schema
- **Objective**: Create consistent tool registration system
- **Actions**:
  - Audit all tool schemas in `axelo/tools/base.py`
  - Add missing tools to schema (especially fetch_js_bundles)
  - Implement validation for tool input/output contracts
  - Create tool capability matrix (what each tool can do)
- **Files**: `axelo/tools/base.py`, `axelo/chat/router.py`
- **Tests**: Unit tests for schema validation

#### Task 1.2: Context Manager Enhancement
- **Objective**: Improve state propagation between tools
- **Actions**:
  - Enhance `ToolState` to support hierarchical context
  - Implement context serialization for checkpoints
  - Add context diffing to track what changed between tools
- **Files**: `axelo/tools/base.py`, `axelo/chat/executor.py`
- **Tests**: Context propagation integration tests

#### Task 1.3: Error Handling Standardization
- **Objective**: Replace all 283 `except: pass` blocks with proper error handling
- **Actions**:
  - Create error handling patterns documentation
  - Replace bare excepts with `except Exception as e: log.warning(...)`
  - Implement retry logic with exponential backoff
  - Add error classification (retryable vs fatal)
- **Files**: All Python files in `axelo/`
- **Tests**: Error scenario unit tests

### Phase 2: AI Orchestration Core (Week 2-3)

#### Task 2.1: Intent Classification System
- **Objective**: Build intelligent request understanding
- **Actions**:
  - Create intent taxonomy (reverse_engineer, crawl, analyze, bypass)
  - Implement pattern matching for intent detection
  - Add fallback to rule-based intent detection when AI unavailable
- **Files**: New file `axelo/orchestration/intent_classifier.py`
- **Tests**: Intent classification accuracy tests

#### Task 2.2: Dynamic Tool Selection Engine
- **Objective**: Replace static tool chain with AI-driven selection
- **Actions**:
  - Implement tool scoring based on site characteristics
  - Create branching logic (simple site → 3 tools, complex → 8+ tools)
  - Add tool dependency resolution
  - Implement tool chain optimization
- **Files**: `axelo/chat/router.py`, new `axelo/orchestration/tool_selector.py`
- **Tests**: Tool selection decision tests

#### Task 2.3: Context-Aware Tool Chain Builder
- **Objective**: Build tool sequences dynamically based on results
- **Actions**:
  - Implement result-based branching (if static finds crypto → add crypto tool)
  - Create tool output validation that triggers next steps
  - Add parallel tool execution for independent operations
- **Files**: `axelo/chat/executor.py`, new `axelo/orchestration/chain_builder.py`
- **Tests**: Chain building integration tests

### Phase 3: Signature Extraction Integration (Week 3-4)

#### Task 3.1: Signature Extractor Integration
- **Objective**: Integrate SignatureExtractor into main tool chain
- **Actions**:
  - Add signature_extractor step in tool chain after static analysis
  - Pass extracted keys to codegen automatically
  - Implement key validation and fallback to placeholder
- **Files**: `axelo/tools/codegen_tool.py`, `axelo/chat/router.py`
- **Tests**: End-to-end key extraction tests

#### Task 3.2: Dynamic Analyzer Integration
- **Objective**: Execute JavaScript in real browser to observe behavior
- **Actions**:
  - Integrate DynamicAnalyzer with browser tool
  - Add script injection for call tracking
  - Implement result parsing for signature inference
- **Files**: `axelo/tools/browser_tool.py`, `axelo/tools/dynamic_analyzer.py`
- **Tests**: Dynamic execution tests

#### Task 3.3: Hypothesis Improvement
- **Objective**: Enhance AI hypothesis generation quality
- **Actions**:
  - Expand prompt engineering with more examples
  - Implement confidence scoring
  - Add hypothesis verification step
  - Create fallback heuristics when AI fails
- **Files**: `axelo/tools/ai_tool.py`
- **Tests**: Hypothesis quality evaluation

### Phase 4: Verification Unification (Week 4-5)

#### Task 4.1: Unified Verification System
- **Objective**: Merge verify_tool and VerificationEngine
- **Actions**:
  - Refactor verify_tool to use VerificationEngine
  - Add anti-bot detection consistency
  - Implement unified reporting format
  - Add verification result caching
- **Files**: `axelo/tools/verify_tool.py`, `axelo/verification/engine.py`
- **Tests**: Verification accuracy tests

#### Task 4.2: Runtime Signature Testing
- **Objective**: Actually test generated signatures against real APIs
- **Actions**:
  - Implement signature validation in verify step
  - Add request replay with captured signatures
  - Create signature comparison metrics
- **Files**: `axelo/tools/sigverify_tool.py`, `axelo/verification/replayer.py`
- **Tests**: Signature validation tests

### Phase 5: Self-Improvement (Week 5-6)

#### Task 5.1: Learning System
- **Objective**: System learns from successful reverse engineering
- **Actions**:
  - Implement pattern library for successful signatures
  - Create feedback loop from verification to tool selection
  - Add success rate tracking per tool combination
- **Files**: New `axelo/orchestration/learning_engine.py`, `axelo/memory/`
- **Tests**: Learning accuracy tests

#### Task 5.2: Adaptive Tool Selection
- **Objective**: System improves tool selection over time
- **Actions**:
  - Track which tool combinations succeed for site types
  - Implement reinforcement learning for tool selection
  - Add A/B testing capability for tool chains
- **Files**: `axelo/orchestration/tool_selector.py`
- **Tests**: Adaptation rate tests

---

## 4. Implementation Roadmap

```
Week 1: Foundation
├── Day 1-2: Tool registry audit
├── Day 3-4: Schema validation implementation  
├── Day 5: Context manager enhancement
└── Weekend: Error handling fixes

Week 2: AI Core
├── Day 6-7: Intent classifier implementation
├── Day 8-9: Dynamic tool selector
├── Day 10: Chain builder prototype
└── Weekend: Integration tests

Week 3: Signature Integration
├── Day 11-12: Signature extractor integration
├── Day 13-14: Dynamic analyzer integration
├── Day 15: Hypothesis improvement
└── Weekend: End-to-end tests

Week 4: Verification
├── Day 16-17: Unified verification system
├── Day 18: Runtime signature testing
├── Day 19: Reporting consolidation
└── Weekend: QA pass

Week 5-6: Self-Improvement
├── Day 20-21: Learning system
├── Day 22-23: Adaptive selection
├── Day 24: Documentation
└── Day 25: Final testing and deployment
```

---

## 5. Key Files to Modify

### 5.1 Files Requiring Major Changes

| File | Change Type | Reason |
|------|-------------|--------|
| `axelo/chat/router.py` | Refactor | Add dynamic tool selection |
| `axelo/chat/executor.py` | Enhance | Add parallel execution, context diffing |
| `axelo/tools/verify_tool.py` | Refactor | Integrate with VerificationEngine |
| `axelo/tools/codegen_tool.py` | Fix | Resolve async/sync issues |
| `axelo/tools/ai_tool.py` | Enhance | Improve hypothesis generation |

### 5.2 New Files to Create

| File | Purpose |
|------|---------|
| `axelo/orchestration/__init__.py` | Orchestration package |
| `axelo/orchestration/intent_classifier.py` | Request intent understanding |
| `axelo/orchestration/tool_selector.py` | Dynamic tool selection |
| `axelo/orchestration/chain_builder.py` | Tool sequence builder |
| `axelo/orchestration/learning_engine.py` | Self-improvement system |

### 5.3 Files with Minor Changes

| File | Change |
|------|--------|
| `axelo/tools/base.py` | Add schema validation |
| `axelo/tools/browser_tool.py` | Add DynamicAnalyzer integration |
| `axelo/tools/signature_extractor.py` | Add sync wrapper |
| `axelo/storage/atomic_writer.py` | Add file locking for concurrent access |

---

## 6. Testing Strategy

### 6.1 Unit Tests

- Tool schema validation tests
- Intent classification tests
- Tool selector decision tests
- Error handling tests

### 6.2 Integration Tests

- Tool chain execution tests
- Context propagation tests
- Signature extraction end-to-end tests

### 6.3 System Tests

- Full reverse engineering workflow tests
- Verification accuracy tests
- Learning system effectiveness tests

### 6.4 Test Coverage Target

| Category | Target |
|----------|--------|
| Unit Tests | 80% |
| Integration Tests | 70% |
| System Tests | 5 key scenarios |

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AI API unavailability | Medium | High | Robust fallback heuristics |
| Complex JS obfuscation | High | Medium | Multiple extraction strategies |
| Anti-bot evolution | High | Medium | Continuous pattern updates |
| Tool chain performance | Low | Low | Caching and parallelization |
| Learning system overfitting | Medium | Low | A/B testing and manual review |

---

## 8. Success Metrics

### 8.1 Technical Metrics

- Tool selection accuracy: >85% (correct tools for site type)
- Signature extraction success: >70% (extract usable keys)
- Hypothesis quality: >80% (AI produces actionable hypotheses)
- Verification accuracy: >90% (correctly identify working code)

### 8.2 Operational Metrics

- Average tool chain length: Adaptive (3-10 tools based on complexity)
- Execution time: <5 minutes for simple sites, <15 minutes for complex
- Success rate: >60% (successful reverse engineering on first attempt)

### 8.3 Self-Improvement Metrics

- Learning improvement: >10% success rate increase over 100 sites
- Tool selection optimization: >5% accuracy improvement per month

---

## 9. Conclusion

This plan transforms Axelo from a linear tool chain into an **AI-centered orchestration system** that:

1. **Intelligently selects** tools based on site characteristics
2. **Dynamically adapts** the tool chain based on intermediate results
3. **Automatically extracts** signature algorithms from JavaScript
4. **Continuously improves** through learning from successful executions

The implementation follows a phased approach, starting with foundation work and progressively adding AI intelligence and self-improvement capabilities.

**Next Steps**: Awaiting approval to begin Phase 1 implementation.

---

*Document Version: 1.0*
*Created: 2026-04-10*
*Status: Pending Approval*