# 全站点通用底层逆向技术增强计划书

## 1. 战略愿景

### 1.1 核心目标

构建一个**通用、强大、可扩展**的底层逆向引擎，能够：

- **自动适应**任何网站的签名机制，无需人工干预
- **通用化处理**所有签名类型（HMAC、AES、RSA、自定义等）
- **全年运行**保持高成功率，减少维护和微调
- **顶尖水平**达到甚至超越专业逆向工程师的能力

### 1.2 当前问题分析

| 问题 | 原因 | 影响 |
|------|------|------|
| **站点依赖** | 每个站点单独处理逻辑 | 需要不断微调 |
| **算法限制** | 只支持常见算法 | 新算法失败 |
| **上下文丢失** | 缺乏整体数据流理解 | 复杂签名无法识别 |
| **动态变化** | 网站更新导致失效 | 维护成本高 |
| **人工介入** | 需要专家配置 | 无法自动化 |

### 1.3 解决方案思路

```
┌─────────────────────────────────────────────────────────────────┐
│                    通用逆向引擎架构                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   输入层    │→ │   处理层    │→ │   输出层    │             │
│  │ (通用接口)  │  │ (AI + 规则)  │  │ (多语言)    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│        ↓                ↓                ↓                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              核心：通用签名推理引擎                      │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │   │
│  │  │ 动态   │ │ 静态   │ │ 加密   │ │ 行为   │         │   │
│  │  │ 追踪器 │ │ 分析器 │ │ 检测器 │ │ 分析器 │         │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 技术架构设计

### 2.1 核心组件

#### 2.1.1 通用输入层 (Universal Input Layer)

**目标**：以不变应万变，接收任何形式的网站输入

```python
class UniversalInputAdapter:
    """
    通用输入适配器 - 将任何网站的流量标准化
    """
    
    def adapt(self, raw_input) -> StandardTraffic:
        # 标准化处理
        # - HTTP 请求/响应
        # - JavaScript 代码
        # - 浏览器 DevTools 协议
        # - 抓包文件 (HAR, PCAP)
        
        return StandardTraffic(
            url=self.normalize_url(raw_input.url),
            headers=self.normalize_headers(raw_input.headers),
            body=self.normalize_body(raw_input.body),
            timing=self.extract_timing(raw_input),
            js_bundles=self.extract_js(raw_input),
        )
```

**关键特性**：
- 支持多种输入格式
- 自动检测编码和加密
- 提取关键时间信息
- 标准化数据格式

#### 2.1.2 通用签名推理引擎 (Universal Signature Inference Engine)

**目标**：无需预先知道算法类型，自动推理签名逻辑

```python
class UniversalSignatureEngine:
    """
    核心引擎：自动推理签名生成逻辑
    """
    
    def __init__(self):
        self.heuristic_matcher = HeuristicMatcher()      # 启发式匹配
        self.ai_analyzer = AIAnalyzer()                  # AI 分析
        self.crypto_detector = CryptoDetector()         # 加密检测
        self.data_flow_tracker = DataFlowTracker()      # 数据流追踪
    
    def infer(self, traffic: StandardTraffic) -> SignatureHypothesis:
        """
        自动推理签名 - 不预设任何算法
        """
        # Step 1: 数据流分析
        data_flows = self.data_flow_tracker.trace(traffic)
        
        # Step 2: 加密特征检测
        crypto_features = self.crypto_detector.detect(traffic.js_bundles)
        
        # Step 3: 启发式模式匹配
        pattern_matches = self.heuristic_matcher.match(traffic)
        
        # Step 4: AI 深度分析
        ai_analysis = self.ai_analyzer.analyze(
            data_flows=data_flows,
            crypto_features=crypto_features,
            pattern_matches=pattern_matches,
        )
        
        # Step 5: 假设生成与验证
        hypothesis = self._synthesize_hypothesis(ai_analysis)
        
        return hypothesis
```

#### 2.1.3 动态自学习系统 (Self-Learning System)

**目标**：从每次成功/失败中学习，自动改进

```python
class AdaptiveLearningSystem:
    """
    自适应学习系统 - 防止失效，持续优化
    """
    
    def __init__(self):
        self.success_patterns = PatternDatabase("success")
        self.failure_patterns = PatternDatabase("failure")
        self.adaptation_rules = AdaptationRules()
    
    def on_success(self, signature, context):
        """从成功案例学习"""
        # 提取成功模式
        pattern = self._extract_pattern(signature, context)
        self.success_patterns.add(pattern)
        self.adaptation_rules.add_rule(pattern)
    
    def on_failure(self, signature, error):
        """从失败案例学习"""
        # 记录失败原因
        failure = self._analyze_failure(error)
        self.failure_patterns.add(failure)
        
        # 自动调整策略
        self._adapt_strategy(failure)
    
    def get_adaptive_hint(self, context) -> dict:
        """获取适应性的提示"""
        return self.adaptation_rules.get_hint(context)
```

---

## 3. 核心技术实现

### 3.1 通用数据流追踪 (Universal Data Flow Tracking)

**问题**：当前系统缺乏完整的数据流理解

**解决方案**：

```python
class UniversalDataFlowTracker:
    """
    通用数据流追踪器 - 追踪任意网站的数据流
    """
    
    def trace(self, traffic: StandardTraffic) -> DataFlowGraph:
        """
        构建完整数据流图
        """
        graph = DataFlowGraph()
        
        # 1. 输入点识别
        input_nodes = self._find_input_points(traffic)
        
        # 2. 转换路径追踪
        for input_node in input_nodes:
            path = self._trace_transformations(input_node, traffic.js_bundles)
            graph.add_path(path)
        
        # 3. 输出点识别
        output_nodes = self._find_output_points(traffic)
        
        # 4. 建立连接
        graph.connect(input_nodes, output_nodes)
        
        return graph
    
    def _find_input_points(self, traffic) -> list[InputPoint]:
        """识别所有输入点"""
        # - URL 参数
        # - 请求头
        # - Cookie
        # - Body 参数
        # - 时间戳
        # - 随机数
        
        return [
            InputPoint(type="param", name="sign", source="url"),
            InputPoint(type="header", name="X-Token", source="request"),
            InputPoint(type="cookie", name="session", source="browser"),
            InputPoint(type="timestamp", name="_t", source="generated"),
            InputPoint(type="nonce", name="nonce", source="generated"),
        ]
    
    def _trace_transformations(self, input_node, js_code) -> list[Transform]:
        """追踪数据转换"""
        transforms = []
        
        # 静态分析：寻找数据处理函数
        static_transforms = self._static_trace(input_node, js_code)
        
        # 动态分析：Hook 运行时行为
        dynamic_transforms = self._dynamic_trace(input_node, js_code)
        
        return static_transforms + dynamic_transforms
    
    def _find_output_points(self, traffic) -> list[OutputPoint]:
        """识别所有输出点"""
        # - 签名 Header
        # - 签名 Query 参数
        # - 签名 Body 字段
        
        return [
            OutputPoint(type="header", name="X-Sign", location="response"),
            OutputPoint(type="query", name="sign", location="next_request"),
        ]
```

### 3.2 通用加密检测器 (Universal Crypto Detector)

**问题**：当前只检测已知算法，无法识别新算法

**解决方案**：

```python
class UniversalCryptoDetector:
    """
    通用加密检测器 - 检测任何加密操作
    """
    
    def __init__(self):
        self.operation_patterns = self._build_operation_patterns()
        self.key_patterns = self._build_key_patterns()
        self.output_patterns = self._build_output_patterns()
    
    def detect(self, js_code: str) -> CryptoAnalysis:
        """检测所有加密操作"""
        
        # 1. 操作识别
        operations = self._identify_operations(js_code)
        
        # 2. 密钥来源分析
        key_sources = self._analyze_key_sources(js_code)
        
        # 3. 输出位置识别
        output_locations = self._find_output_locations(js_code)
        
        # 4. 模式合成
        crypto_pattern = self._synthesize_pattern(
            operations, key_sources, output_locations
        )
        
        return CryptoAnalysis(
            operations=operations,
            key_sources=key_sources,
            output_locations=output_locations,
            pattern=crypto_pattern,
            confidence=self._calculate_confidence(crypto_pattern),
        )
    
    def _build_operation_patterns(self) -> dict:
        """构建操作模式"""
        return {
            # 已知操作
            "hmac": [
                r"createHmac",
                r"HmacSHA",
                r"\.hmac\(",
            ],
            "aes": [
                r"AES\.encrypt",
                r"createCipher",
            ],
            # 未知操作 - 通用模式
            "obfuscated_call": [
                # 函数调用模式
                r"\w+\s*\([^)]*(?:key|secret|sign)\s*\)",
                # 对象方法调用
                r"\w+\.\w+\s*\([^)]*sign",
            ],
            "inline_crypto": [
                # 内联加密
                r"(?:xor|shift|rotate)\s*\(",
                r"(?:\|\||\&\&).*(?:\|\||\&\&)",
            ],
        }
    
    def _identify_operations(self, js_code) -> list[CryptoOperation]:
        """识别所有加密操作"""
        operations = []
        
        for op_type, patterns in self.operation_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, js_code)
                for match in matches:
                    operations.append(CryptoOperation(
                        type=op_type,
                        code_snippet=match.group(),
                        location=self._get_location(js_code, match.start()),
                        confidence=self._estimate_confidence(op_type, match.group()),
                    ))
        
        # 按位置排序
        operations.sort(key=lambda x: x.location.line)
        
        return operations
```

### 3.3 通用启发式匹配器 (Universal Heuristic Matcher)

**问题**：依赖预设模式，无法适应新网站

**解决方案**：

```python
class UniversalHeuristicMatcher:
    """
    通用启发式匹配器 - 从任意网站提取特征
    """
    
    def __init__(self):
        self.pattern_library = AdaptivePatternLibrary()
    
    def match(self, traffic: StandardTraffic) -> HeuristicResult:
        """通用启发式匹配"""
        
        results = {
            "url_patterns": self._match_url_patterns(traffic),
            "header_patterns": self._match_header_patterns(traffic),
            "body_patterns": self._match_body_patterns(traffic),
            "js_patterns": self._match_js_patterns(traffic),
            "timing_patterns": self._match_timing_patterns(traffic),
        }
        
        # 综合评分
        score = self._calculate_composite_score(results)
        
        return HeuristicResult(
            patterns=results,
            composite_score=score,
            recommendations=self._generate_recommendations(results),
        )
    
    def _match_url_patterns(self, traffic) -> list[Pattern]:
        """URL 参数模式匹配"""
        patterns = []
        
        # 检查常见签名参数名
        sign_params = ["sign", "signature", "_s", "_sign", "x_sign"]
        for param in sign_params:
            if param in traffic.url.params:
                patterns.append(Pattern(
                    type="signature_param",
                    name=param,
                    confidence=0.9,
                    context="URL parameter",
                ))
        
        # 检查参数顺序
        param_order = list(traffic.url.params.keys())
        if self.pattern_library.knows_order(param_order):
            patterns.append(Pattern(
                type="parameter_order",
                value=param_order,
                confidence=self.pattern_library.get_order_confidence(param_order),
            ))
        
        return patterns
    
    def _match_header_patterns(self, traffic) -> list[Pattern]:
        """请求头模式匹配"""
        patterns = []
        
        # 检查签名相关 Header
        sign_headers = [
            "X-Sign", "X-Signature", "X-Token", "X-Api-Key",
            "Authorization", "X-Check", "X-Validate",
        ]
        
        for header in sign_headers:
            if header in traffic.request.headers:
                patterns.append(Pattern(
                    type="signature_header",
                    name=header,
                    confidence=0.85,
                    value=traffic.request.headers[header][:50],  # 截断敏感值
                ))
        
        return patterns
```

---

## 4. 自适应学习系统

### 4.1 模式自适应

```python
class AdaptivePatternLibrary:
    """
    自适应模式库 - 从实践中学习
    """
    
    def __init__(self):
        self.patterns = {}  # type -> [patterns]
        self.statistics = PatternStatistics()
    
    def learn_from_success(self, signature: SignatureHypothesis):
        """从成功案例学习"""
        
        # 提取特征模式
        features = {
            "algorithm": signature.algorithm,
            "key_source": signature.key_source,
            "parameter_order": signature.parameter_order,
            "header_location": signature.output_location,
            "input_sources": signature.input_sources,
        }
        
        # 更新模式库
        for key, value in features.items():
            if key not in self.patterns:
                self.patterns[key] = []
            self.patterns[key].append(value)
        
        # 更新统计
        self.statistics.record_success(features)
    
    def learn_from_failure(self, signature: SignatureHypothesis, error: str):
        """从失败案例学习"""
        
        # 记录失败模式
        self.statistics.record_failure({
            "signature": signature.to_dict(),
            "error": error,
            "timestamp": time.time(),
        })
        
        # 调整权重
        self._adjust_weights(signature, error)
    
    def get_hint(self, context: dict) -> dict:
        """根据上下文获取提示"""
        
        # 基于历史统计生成提示
        hints = []
        
        # 算法提示
        if "js_code" in context:
            detected = detect_algorithms(context["js_code"])
            for algo in detected:
                success_rate = self.statistics.get_success_rate(algo)
                if success_rate > 0.7:
                    hints.append({
                        "type": "algorithm",
                        "value": algo,
                        "confidence": success_rate,
                    })
        
        # 参数顺序提示
        if "url_params" in context:
            order = list(context["url_params"].keys())
            if self.knows_order(order):
                hints.append({
                    "type": "parameter_order",
                    "value": order,
                    "confidence": self.get_order_confidence(order),
                })
        
        return {"hints": hints, "source": "adaptive_learning"}
```

### 4.2 失效检测与恢复

```python
class AdaptiveFailureDetector:
    """
    失效检测与自动恢复系统
    """
    
    def __init__(self):
        self.health_monitor = HealthMonitor()
        self.fallback_strategies = FallbackStrategies()
    
    async def detect_and_recover(self, crawler, test_request) -> RecoveryResult:
        """检测失效并尝试恢复"""
        
        # Step 1: 执行测试请求
        try:
            response = await crawler.execute(test_request)
        except Exception as e:
            return await self._handle_error(e, crawler)
        
        # Step 2: 检查响应有效性
        if not self._is_valid_response(response):
            # 可能是签名失效
            diagnosis = await self._diagnose_failure(crawler, response)
            
            # Step 3: 尝试恢复
            if diagnosis.can_fix:
                recovery = await self._attempt_recovery(crawler, diagnosis)
                return recovery
            else:
                return RecoveryResult(
                    success=False,
                    reason=diagnosis.reason,
                    requires_manual=True,
                )
        
        return RecoveryResult(success=True)
    
    async def _attempt_recovery(self, crawler, diagnosis) -> RecoveryResult:
        """尝试恢复"""
        
        # 尝试不同策略
        for strategy in self.fallback_strategies.get_strategies(diagnosis):
            try:
                result = await strategy.apply(crawler)
                if result.success:
                    return result
            except Exception as e:
                log.warning("recovery_strategy_failed", strategy=strategy.name, error=str(e))
                continue
        
        return RecoveryResult(success=False, reason="All recovery strategies failed")
```

---

## 5. 实施路线图

### 5.1 阶段一：基础架构 (Month 1-2)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 通用输入适配器 | 支持多种输入格式 | `universal_input.py` |
| 标准化数据格式 | 统一内部表示 | `standard_traffic.py` |
| 基础数据流追踪 | 追踪输入到输出 | `data_flow_tracker.py` |
| 基础加密检测 | 检测已知算法 | `crypto_detector.py` |

### 5.2 阶段二：推理引擎 (Month 3-4)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 签名推理引擎 | 自动推理签名 | `signature_inference.py` |
| 启发式匹配器 | 通用模式匹配 | `heuristic_matcher.py` |
| AI 集成 | 深度分析能力 | `ai_integration.py` |
| 假设验证 | 自动验证假设 | `hypothesis_verifier.py` |

### 5.3 阶段三：自适应学习 (Month 5-6)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 模式库 | 从实践学习 | `adaptive_patterns.py` |
| 失效检测 | 自动发现问题 | `failure_detector.py` |
| 自动恢复 | 自动修复问题 | `auto_recovery.py` |
| 统计系统 | 持续监控优化 | `statistics.py` |

### 5.4 阶段四：优化与整合 (Month 7-8)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 性能优化 | 提升处理速度 | `optimizer.py` |
| 系统整合 | 统一接口 | `integration.py` |
| 全面测试 | 验证通用性 | `test_suite.py` |
| 文档 | 完整文档 | `docs/` |

---

## 6. 预期成果

### 6.1 核心指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| **成功率** | ~60% | >90% | +50% |
| **自动化程度** | 需要配置 | 全自动 | +100% |
| **适应性** | 需微调 | 免维护 | +200% |
| **通用性** | 针对站点 | 通用 | +300% |
| **维护成本** | 高 | 极低 | -80% |

### 6.2 能力提升

- **任何网站**：只需输入 URL，自动完成逆向
- **任何算法**：自动检测和适配 HMAC、AES、RSA 等
- **任何变化**：自动适应网站更新，无需人工干预
- **持续学习**：越用越强，不断优化

### 6.3 技术优势

```python
# 使用示例
from axelo.core import UniversalReverseEngine

engine = UniversalReverseEngine()

# 只需一行代码
result = await engine.reverse("https://any-website.com/api")

# 自动完成：
# 1. 流量捕获
# 2. 数据流分析
# 3. 加密检测
# 4. 签名推理
# 5. 代码生成
# 6. 验证测试

print(result.crawler_code)  # 生成的可执行代码
print(result.confidence)    # 置信度 > 90%
```

---

## 7. 风险管理

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **AI 成本** | 可能很高 | 使用本地模型，优化提示 |
| **复杂度** | 可能过度设计 | 模块化，逐步实现 |
| **性能** | 处理速度可能慢 | 优化算法，并行处理 |
| **准确性** | 可能误判 | 多重验证，自适应学习 |

---

## 8. 预算估算

| 阶段 | 预估小时 | AI Tokens | 外部依赖 |
|------|----------|-----------|----------|
| 阶段一 | 80h | 5000 | 无 |
| 阶段二 | 120h | 10000 | 无 |
| 阶段三 | 80h | 5000 | 可选 (本地模型) |
| 阶段四 | 40h | 2000 | 无 |
| **总计** | **320h** | **22000** | **可选** |

---

## 9. 成功标准

### 9.1 量化指标

- [ ] 成功率 ≥ 90%
- [ ] 平均处理时间 < 5 分钟
- [ ] 维护成本降低 80%
- [ ] 支持 100+ 网站类型

### 9.2 质量指标

- [ ] 无需人工配置
- [ ] 自动适应变化
- [ ] 持续自学习优化
- [ ] 完整可复现性

---

**计划版本**: 1.0  
**创建日期**: 2026-04-07  
**预计完成**: 8 个月  
**状态**: 等待审批