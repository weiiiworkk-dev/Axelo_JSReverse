# 模块集成计划书

## 1. 当前状态分析

### 1.1 新建模块清单

| 模块 | 路径 | 功能 | 集成状态 |
|------|------|------|----------|
| **行为模拟器** | `axelo/behavior/mouse_simulator.py` | 鼠标/键盘/滚动模拟 | ❌ 未集成 |
| **蜜罐检测器** | `axelo/detection/honeypot_detector.py` | 陷阱检测 | ❌ 未集成 |
| **频率控制器** | `axelo/rate_control/adaptive_limiter.py` | 请求频率控制 | ❌ 未集成 |
| **签名失效检测** | `axelo/detection/signature_failure.py` | 自动恢复 | ❌ 未集成 |
| **设备指纹强化** | `axelo/fingerprint/fingerprint_reinforcer.py` | 指纹生成 | ❌ 未集成 |
| **自适应学习** | `axelo/learning/adaptive_learning.py` | 持续学习 | ❌ 未集成 |

### 1.2 现有系统架构

```
MasterOrchestrator (axelo/orchestrator/master.py)
    │
    ├── DiscoveryFlow      ← 需要集成蜜罐检测
    ├── AnalysisFlow       ← 需要集成行为模拟
    ├── DeliveryFlow       ← 需要集成签名检测
    └── Pipeline Stages
        ├── s1_crawl.py     ← 需要集成频率控制、行为模拟
        ├── s2_fetch.py
        ├── s3_deobfuscate.py
        ├── s4_static.py
        ├── s5_dynamic.py
        ├── s6_ai_analyze.py ← 需要集成自适应学习
        ├── s7_codegen.py
        └── s8_verify.py    ← 需要集成签名失效检测
```

### 1.3 需要集成的模块依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                    集成依赖关系图                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Pipeline Stage 1 (s1_crawl.py)                           │  │
│  │  - 行为模拟器 (mouse_simulator)                          │  │
│  │  - 频率控制器 (adaptive_limiter)                         │  │
│  │  - 蜜罐检测器 (honeypot_detector)                         │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Pipeline Stage 6 (s6_ai_analyze.py)                     │  │
│  │  - 自适应学习系统 (adaptive_learning)                    │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Pipeline Stage 8 (s8_verify.py)                          │  │
│  │  - 签名失效检测 (signature_failure)                      │  │
│  └─────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Browser Driver (browser/driver.py)                      │  │
│  │  - 设备指纹强化 (fingerprint_reinforcer)                 │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 集成计划

### 2.1 第一阶段：行为模拟集成 (Priority: High)

**目标**: 在爬取阶段集成行为模拟，提升反检测能力

#### 任务 1.1: 修改 s1_crawl.py

```python
# 在 Crawler 类中添加行为模拟
from axelo.behavior.mouse_simulator import (
    MouseMovementSimulator,
    KeyboardSimulator,
    ScrollSimulator,
    IdlePatternGenerator,
)

class Crawler:
    def __init__(self):
        # ... existing code ...
        self.mouse_sim = MouseMovementSimulator()
        self.keyboard_sim = KeyboardSimulator()
        self.scroll_sim = ScrollSimulator()
        self.idle_gen = IdlePatternGenerator()
    
    async def click_element(self, selector):
        await self.mouse_sim.move_to_element(self.page, selector)
    
    async def type_text(self, selector, text):
        await self.keyboard_sim.type_text(self.page, text, selector)
```

#### 任务 1.2: 修改 browser/driver.py

```python
# 在 BrowserDriver 中添加行为模拟支持
from axelo.behavior.mouse_simulator import create_behavior_simulator

class BrowserDriver:
    def __init__(self):
        # ... existing code ...
        self.behavior = create_behavior_simulator()
    
    async def human_like_click(self, selector):
        await self.behavior["mouse"].move_to_element(self.page, selector)
```

---

### 2.2 第二阶段：频率控制集成 (Priority: High)

**目标**: 在请求层集成自适应频率控制

#### 任务 2.1: 创建请求拦截器

```python
# axelo/network/rate_limiter.py
from axelo.rate_control.adaptive_limiter import AdaptiveRateController

class RequestInterceptor:
    def __init__(self):
        self.rate_controller = AdaptiveRateController()
    
    async def request(self, method, url, **kwargs):
        # Wait if needed
        domain = extract_domain(url)
        await self.rate_controller.acquire(domain)
        
        # Make request
        response = await self._make_request(method, url, **kwargs)
        
        # Record response
        self.rate_controller.on_response(
            domain, 
            response_time=response.elapsed,
            status_code=response.status_code
        )
        
        return response
```

#### 任务 2.2: 集成到 Crawler

```python
# 在 Crawler 中使用拦截器
class Crawler:
    def __init__(self):
        self.interceptor = RequestInterceptor()
    
    async def get(self, url, **kwargs):
        return await self.interceptor.request("GET", url, **kwargs)
```

---

### 2.3 第三阶段：蜜罐检测集成 (Priority: High)

**目标**: 在页面分析阶段集成蜜罐检测

#### 任务 3.1: 修改 s1_crawl.py - 页面扫描

```python
from axelo.detection.honeypot_detector import HoneypotDetector, HoneypotAwareActionRunner

class Crawler:
    def __init__(self):
        # ... existing code ...
        self.honeypot_detector = HoneypotDetector()
        self.honeypot_runner = None
    
    async def scan_page(self):
        report = await self.honeypot_detector.scan_page(self.page)
        
        if report.has_traps:
            log.warning("honeypot_detected", 
                       fields=len(report.hidden_fields),
                       links=len(report.trap_links))
        
        # Create honeypot-aware action runner
        self.honeypot_runner = HoneypotAwareActionRunner(self.page)
        await self.honeypot_runner.initialize()
        
        return report
```

#### 任务 3.2: 修改 Action Runner

```python
# 使用安全的点击和输入方法
async def safe_click(self, selector):
    if self.honeypot_runner:
        return await self.honeypot_runner.safe_click(selector)
    else:
        await self.page.click(selector)
```

---

### 2.4 第四阶段：设备指纹集成 (Priority: Medium)

**目标**: 在浏览器启动时生成强化的设备指纹

#### 任务 4.1: 修改 browser/driver.py

```python
from axelo.fingerprint.fingerprint_reinforcer import DeviceFingerprintReinforcer

class BrowserDriver:
    def __init__(self):
        # ... existing code ...
        self.fingerprint_reinforcer = DeviceFingerprintReinforcer()
    
    async def launch(self, profile):
        # ... existing code ...
        
        # Generate enhanced fingerprint
        fingerprint = self.fingerprint_reinforcer.generate_fingerprint(
            profile=profile,
            page=self._page
        )
        
        # Inject fingerprint (if supported by simulation)
        # This enhances the existing device coherence checks
        log.info("fingerprint_generated",
                canvas=fingerprint.canvas_hash[:16],
                audio=fingerprint.audio_hash[:16])
        
        return self._page
```

#### 任务 4.2: 修改 browser/device_coherence.py

```python
# 集成到现有的设备一致性检查
from axelo.fingerprint.fingerprint_reinforcer import DeviceFingerprintReinforcer

def validate_profile_coherence(...):
    # ... existing code ...
    
    # Use the reinforcer for additional checks
    reinforcer = DeviceFingerprintReinforcer()
    
    return violations
```

---

### 2.5 第五阶段：签名失效检测集成 (Priority: High)

**目标**: 在验证阶段集成签名失效检测和自动恢复

#### 任务 5.1: 修改 s8_verify.py

```python
from axelo.detection.signature_failure import (
    SignatureFailureDetector,
    create_failure_detector
)

class VerificationEngine:
    def __init__(self):
        # ... existing code ...
        self.failure_detector = create_failure_detector()
    
    async def verify_and_recover(self, crawler, test_request):
        # Try verification
        result = await self.verify(test_request)
        
        if not result.success:
            # Attempt recovery
            recovery = await self.failure_detector.detect_and_recover(
                crawler, test_request
            )
            
            if recovery.success:
                log.info("recovery_successful", strategy=recovery.strategy)
                return await self.verify(test_request)  # Retry
        
        return result
```

#### 任务 5.2: 修改 orchestrator/recovery.py

```python
# 集成到现有的恢复机制
from axelo.detection.signature_failure import RecoveryStrategyRegistry

class RecoveryManager:
    def __init__(self):
        # ... existing code ...
        self.strategy_registry = RecoveryStrategyRegistry()
    
    async def handle_failure(self, error, context):
        # ... existing code ...
        
        # Use signature failure strategies
        diagnosis = self._diagnose(error)
        strategies = self.strategy_registry.get_strategies(diagnosis)
        
        for strategy in strategies:
            result = await strategy.execute(context)
            if result.success:
                return result
```

---

### 2.6 第六阶段：自适应学习集成 (Priority: Medium)

**目标**: 在 AI 分析阶段集成自适应学习

#### 任务 6.1: 修改 s6_ai_analyze.py

```python
from axelo.learning.adaptive_learning import (
    AdaptiveLearningSystem,
    create_learning_system
)

class AIAnalyzer:
    def __init__(self):
        # ... existing code ...
        self.learning_system = create_learning_system()
    
    async def analyze(self, traffic, context):
        # ... existing analysis ...
        
        # Get optimized strategy
        strategy = self.learning_system.get_optimized_strategy(
            RequestContext(
                domain=traffic.domain,
                url=traffic.url,
                method="GET",
                headers={},
                timestamp=time.time()
            )
        )
        
        # Apply strategy adjustments
        if strategy.get("adjustments"):
            log.info("strategy_adjusted",
                    adjustments=strategy["adjustments"])
        
        return analysis_result
    
    async def learn(self, context, result):
        # Learn from result
        await self.learning_system.learn_from_result(context, result)
```

#### 任务 6.2: 修改 core/__init__.py

```python
# 将新模块集成到 UniversalReverseEngine
from axelo.learning.adaptive_learning import AdaptiveLearningSystem

class UniversalReverseEngine:
    def __init__(self):
        # ... existing code ...
        # 使用已有的 learning system 或新模块
        self.learning_system = AdaptiveLearningSystem()
```

---

## 3. 实施顺序

```
阶段 1: 行为模拟 (s1_crawl.py + browser/driver.py)
    ↓
阶段 2: 频率控制 (创建请求拦截器)
    ↓
阶段 3: 蜜罐检测 (s1_crawl.py 页面扫描)
    ↓
阶段 4: 设备指纹 (browser/driver.py)
    ↓
阶段 5: 签名失效检测 (s8_verify.py + recovery.py)
    ↓
阶段 6: 自适应学习 (s6_ai_analyze.py)
```

---

## 4. 需要的修改文件清单

| 优先级 | 文件 | 修改内容 |
|--------|------|----------|
| P0 | `axelo/pipeline/stages/s1_crawl.py` | 集成行为模拟、频率控制、蜜罐检测 |
| P0 | `axelo/browser/driver.py` | 集成设备指纹强化 |
| P1 | `axelo/pipeline/stages/s8_verify.py` | 集成签名失效检测与恢复 |
| P1 | `axelo/orchestrator/recovery.py` | 集成恢复策略 |
| P2 | `axelo/pipeline/stages/s6_ai_analyze.py` | 集成自适应学习 |
| P2 | `axelo/core/__init__.py` | 统一入口更新 |
| P3 | `axelo/network/` | 创建请求拦截器 |

---

## 5. 风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 现有代码冲突 | 新模块可能与现有逻辑冲突 | 使用组合模式，不修改现有逻辑 |
| 性能开销 | 行为模拟增加延迟 | 异步执行，按需启用 |
| 集成复杂度 | 多模块协同复杂 | 分阶段集成，逐步测试 |

---

## 6. 成功标准

- [ ] 行为模拟在 s1_crawl 中可用
- [ ] 频率控制自动调整请求间隔
- [ ] 蜜罐检测识别陷阱字段
- [ ] 设备指纹强化在浏览器启动时生成
- [ ] 签名失效检测在验证失败时触发
- [ ] 自适应学习记录成功/失败模式

---

**计划版本**: 1.0  
**创建日期**: 2026-04-07  
**状态**: 等待审批