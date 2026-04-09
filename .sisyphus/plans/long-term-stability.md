# 全站点底层通用长期稳定性增强计划书

## 1. 战略愿景

### 1.1 核心目标

构建一个**全年稳定运行、符合风控对抗需求、通用化处理**的底层逆向引擎，能够：

- **无限期运行**：无需人工干预即可长期稳定运行
- **风控免疫**：全面应对各类风控检测机制
- **通用底层**：不针对特定站点，完全基于底层技术
- **自愈能力**：自动检测失效并恢复
- **持续进化**：从每次成功/失败中持续学习优化

### 1.2 风控对抗全景

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            风控对抗系统架构                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        防御层 (Defense Layer)                          │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │   │
│   │  │ 浏览器   │ │ 设备指纹 │ │ TLS/SSL  │ │ 请求频率 │ │ 行为模式 │      │   │
│   │  │ 伪装     │ │ 一致性   │ │ 指纹     │ │ 控制     │ │ 模拟     │      │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        检测层 (Detection Layer)                        │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │   │
│   │  │ 风控信号 │ │ 蜜罐检测 │ │ 验证码   │ │ 签名失效 │ │ 设备指纹 │      │   │
│   │  │ 识别     │ │         │ │ 识别     │ │ 检测     │ │ 异常     │      │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        响应层 (Response Layer)                          │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │   │
│   │  │ 自动恢复 │ │ 代理轮换 │ │ 会话切换 │ │ 策略调整 │ │ 模式切换 │      │   │
│   │  │         │ │         │ │         │ │         │ │         │      │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        学习层 (Learning Layer)                          │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │   │
│   │  │ 成功模式 │ │ 失败模式 │ │ 策略库   │ │ 权重调整 │ │ 预测模型 │      │   │
│   │  │ 提取     │ │ 分析     │ │ 更新     │ │         │ │         │      │   │
│   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 当前系统能力评估

| 维度 | 现有能力 | 评级 | 差距 |
|------|----------|------|------|
| **浏览器伪装** | 20+反检测标志、自动化检测 | ⭐⭐⭐⭐ | 需增加行为模拟 |
| **设备指纹** | TLS指纹、WebGL一致性 | ⭐⭐⭐⭐ | 需增强Canvas/Audio |
| **代理管理** | 轮换、阻止标记、健康评分 | ⭐⭐⭐ | 需智能IP池 |
| **风控检测** | 403/429/503检测、错误码 | ⭐⭐⭐⭐ | 需增强蜜罐检测 |
| **验证码处理** | 基本检测 | ⭐⭐ | 需自动解决能力 |
| **签名失效** | 基础检测 | ⭐⭐ | 需自动恢复 |
| **行为模拟** | 无 | ⭐ | 需完整实现 |
| **自适应学习** | 无 | ⭐ | 需完整实现 |

---

## 2. 技术架构设计

### 2.1 核心组件

#### 2.1.1 行为模拟引擎 (Behavior Simulation Engine)

**目标**：模拟真实用户行为，躲避行为分析风控

```python
class BehaviorSimulator:
    """
    行为模拟器 - 模拟真实用户操作模式
    """
    
    def __init__(self):
        self.mouse_simulator = MouseMovementSimulator()
        self.keyboard_simulator = KeyboardSimulator()
        self.scroll_simulator = ScrollPatternSimulator()
        self.idle_detector = IdlePatternGenerator()
    
    async def simulate_human_behavior(self, page, action_type: str):
        """根据操作类型模拟相应的人类行为"""
        
        if action_type == "click":
            await self.mouse_simulator.human_like_click(page)
        elif action_type == "type":
            await self.keyboard_simulator.human_typing(page)
        elif action_type == "scroll":
            await self.scroll_simulator.natural_scroll(page)
        elif action_type == "idle":
            await self.idle_detector.random_idle(page)


class MouseMovementSimulator:
    """鼠标移动模拟 - 躲避轨迹分析"""
    
    def __init__(self):
        self.velocity_model = VelocityModel()
        self.jitter_generator = JitterGenerator()
    
    async def human_like_click(self, page, target_selector: str):
        """模拟人类点击：先移动到目标，再点击"""
        
        # 获取目标元素位置
        target = await page.locator(target_selector).bounding_box()
        
        # 计算移动路径（贝塞尔曲线 + 随机抖动）
        path = self._generate_natural_path(
            start=self._current_position,
            end=target,
            duration=random.uniform(300, 800),  # 300-800ms 移动时间
        )
        
        # 执行路径（带加速度变化）
        for point in path:
            await page.mouse.move(point.x, point.y)
            await asyncio.sleep(0.016)  # 60fps
        
        # 点击（带轻微抖动）
        await page.mouse.click(
            target.x + random.uniform(-2, 2),
            target.y + random.uniform(-2, 2),
        )
    
    def _generate_natural_path(self, start, end, duration):
        """生成自然的移动路径"""
        # 使用缓动函数 + 随机偏移
        points = []
        steps = int(duration / 16)  # 60fps
        
        for i in range(steps):
            t = i / steps
            # 缓动函数（Ease-out）
            eased = 1 - pow(1 - t, 3)
            
            # 基础位置
            x = start.x + (end.x - start.x) * eased
            y = start.y + (end.y - start.y) * eased
            
            # 添加随机抖动
            jitter = self.jitter_generator.get_jitter(t)
            x += jitter.x
            y += jitter.y
            
            points.append(Point(x, y))
        
        return points


class VelocityModel:
    """速度模型 - 真实人类鼠标移动速度变化"""
    
    # 速度分布：人类移动速度服从对数正态分布
    # 平均速度约 30-50 pixels/second
    
    def get_velocity_at(self, progress: float) -> float:
        """根据进度返回当前速度"""
        
        # 移动开始：加速
        if progress < 0.2:
            return self._accelerating_phase(progress)
        # 移动中间：匀速（带波动）
        elif progress < 0.8:
            return self._cruising_phase(progress)
        # 移动结束：减速
        else:
            return self._decelerating_phase(progress)
    
    def _accelerating_phase(self, p):
        base = 20 + p * 100  # 20 -> 40
        return base + random.gauss(0, 10)
    
    def _cruising_phase(self, p):
        base = 40 + math.sin(p * 10) * 15  # 波动
        return base + random.gauss(0, 8)
    
    def _decelerating_phase(self, p):
        base = 40 - (p - 0.8) * 150  # 40 -> 10
        return max(5, base + random.gauss(0, 5))
```

#### 2.1.2 蜜罐检测系统 (Honeypot Detection System)

**目标**：识别并避开网站设置的陷阱

```python
class HoneypotDetector:
    """
    蜜罐检测器 - 识别隐藏的陷阱链接/字段
    """
    
    def __init__(self):
        self.hidden_field_patterns = self._compile_patterns()
        self.trap_link_patterns = self._compile_trap_patterns()
        self.decoy_patterns = self._compile_decoy_patterns()
    
    def scan_page(self, page) -> HoneypotReport:
        """扫描页面并生成蜜罐报告"""
        
        report = HoneypotReport()
        
        # 1. 检查隐藏表单字段
        report.hidden_fields = await self._find_hidden_fields(page)
        
        # 2. 检查陷阱链接
        report.trap_links = await self._find_trap_links(page)
        
        # 3. 检查诱饵数据
        report.decoy_data = await self._find_decoy_data(page)
        
        # 4. 检查CSS陷阱
        report.css_traps = await self._find_css_traps(page)
        
        # 5. 计算风险评分
        report.risk_score = self._calculate_risk(report)
        
        return report
    
    async def _find_hidden_fields(self, page) -> list[HiddenField]:
        """查找隐藏表单字段"""
        
        fields = await page.evaluate("""
            () => {
                const fields = [];
                document.querySelectorAll('input, select, textarea').forEach(el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    
                    // 隐藏字段特征
                    const isHidden = 
                        style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        style.opacity === '0' ||
                        rect.width === 0 ||
                        rect.height === 0;
                    
                    // 可能是蜜罐的字段名
                    const suspiciousNames = [
                        'honeypot', 'trap', 'bot', 'spam', 'fake',
                        'hidden', 'secret', 'confirm', 'anti'
                    ];
                    
                    const name = el.name || el.id || '';
                    const isSuspicious = suspiciousNames.some(s => 
                        name.toLowerCase().includes(s)
                    );
                    
                    if (isHidden || isSuspicious) {
                        fields.push({
                            tag: el.tagName,
                            name: name,
                            type: el.type,
                            value: el.value,
                            hidden: isHidden,
                            suspicious: isSuspicious
                        });
                    }
                });
                return fields;
            }
        """)
        
        return [HiddenField(**f) for f in fields]
    
    async def _find_trap_links(self, page) -> list[TrapLink]:
        """查找陷阱链接（不可见或看似无害的链接）"""
        
        links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a').forEach(el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    
                    // 检查是否可见
                    const isVisible = 
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        rect.width > 0 && rect.height > 0 &&
                        style.opacity !== '0';
                    
                    // 检查链接文本/URL
                    const text = el.textContent || '';
                    const href = el.href || '';
                    
                    // 陷阱链接特征
                    const suspiciousPatterns = [
                        'click', 'track', 'ad', 'promo', 'gift',
                        'winner', 'claim', 'free', 'offer'
                    ];
                    
                    const isSuspicious = 
                        suspiciousPatterns.some(p => text.toLowerCase().includes(p)) ||
                        suspiciousPatterns.some(p => href.toLowerCase().includes(p));
                    
                    // 检查是否在可见区域外
                    const isOffScreen = 
                        rect.top > window.innerHeight ||
                        rect.left > window.innerWidth;
                    
                    if (!isVisible || isOffScreen || isSuspicious) {
                        links.push({
                            text: text.substring(0, 50),
                            href: href,
                            visible: isVisible,
                            offscreen: isOffScreen,
                            suspicious: isSuspicious
                        });
                    }
                });
                return links;
            }
        """)
        
        return [TrapLink(**l) for l in links]
    
    def should_avoid(self, element: dict) -> bool:
        """判断是否应该避开某个元素"""
        
        # 蜜罐字段：永远不填写
        if element.get("hidden") and element.get("suspicious"):
            return True
        
        # 陷阱链接：永远不点击
        if element.get("type") == "trap_link":
            return True
        
        return False
```

#### 2.1.3 请求频率控制器 (Rate Limiter)

**目标**：控制请求频率以躲避频率风控

```python
class AdaptiveRateController:
    """
    自适应频率控制器 - 根据目标响应动态调整请求速率
    """
    
    def __init__(self):
        self.pacing_model = PacingModel()
        self.response_analyzer = ResponseAnalyzer()
        self.strategy_selector = StrategySelector()
        self.current_strategy = "conservative"
        self._request_times: list[float] = []
        self._error_times: list[float] = []
    
    async def acquire(self, domain: str) -> None:
        """获取请求许可（可能需要等待）"""
        
        strategy = self.strategy_selector.get_strategy(
            domain, 
            self._get_recent_metrics()
        )
        self.current_strategy = strategy.name
        
        # 计算最小等待时间
        min_interval = strategy.get_min_interval(
            self._get_domain_history(domain)
        )
        
        # 计算自适应的等待时间
        adaptive_delay = self._calculate_adaptive_delay(
            domain, min_interval
        )
        
        if adaptive_delay > 0:
            log.info("rate_limit_waiting", 
                    domain=domain, 
                    delay_ms=adaptive_delay)
            await asyncio.sleep(adaptive_delay / 1000)
    
    def _calculate_adaptive_delay(self, domain: str, base_delay: float) -> float:
        """根据响应质量计算自适应延迟"""
        
        recent_responses = self._get_recent_responses(domain, n=10)
        
        if not recent_responses:
            return 0
        
        # 分析错误率
        error_rate = sum(1 for r in recent_responses if r.is_error) / len(recent_responses)
        
        # 分析响应时间波动
        response_times = [r.response_time for r in recent_responses if not r.is_error]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            variance = sum((t - avg_time) ** 2 for t in response_times) / len(response_times)
            std_dev = variance ** 0.5
            
            # 响应时间波动大 = 风控信号
            if std_dev > avg_time * 0.5:
                return base_delay * 2
        
        # 根据错误率调整
        if error_rate > 0.3:
            return base_delay * 3  # 高错误率：大幅降低
        elif error_rate > 0.1:
            return base_delay * 1.5  # 中错误率：适度降低
        
        return base_delay
    
    def on_response(self, domain: str, response: Response) -> None:
        """记录响应以调整策略"""
        
        self._request_times.append(time.time())
        
        if response.is_error:
            self._error_times.append(time.time())
        
        # 定期清理历史数据
        self._cleanup_old_data()
        
        # 更新 pacing model
        self.pacing_model.update(domain, response)


class PacingModel:
    """节奏模型 - 基于历史数据学习最优请求节奏"""
    
    def __init__(self):
        self._domain_histories: dict[str, DomainHistory] = {}
    
    def update(self, domain: str, response: Response) -> None:
        """更新域名的节奏历史"""
        
        if domain not in self._domain_histories:
            self._domain_histories[domain] = DomainHistory()
        
        self._domain_histories[domain].add(response)
    
    def get_recommended_interval(self, domain: str) -> float:
        """获取推荐的请求间隔"""
        
        history = self._domain_histories.get(domain)
        if not history:
            return 1000  # 默认1秒
        
        # 基于成功率计算
        success_rate = history.success_rate
        avg_response_time = history.avg_response_time
        
        # 成功率越高，可以越快
        # 响应时间越长，应该越慢
        base = max(500, min(5000, avg_response_time * 2))
        
        if success_rate > 0.9:
            return base * 0.5
        elif success_rate > 0.7:
            return base
        elif success_rate > 0.5:
            return base * 2
        else:
            return base * 4
```

#### 2.1.4 签名失效检测与恢复系统 (Signature Failure Detector)

**目标**：自动检测签名失效并自动恢复

```python
class SignatureFailureDetector:
    """
    签名失效检测与自动恢复系统
    """
    
    def __init__(self):
        self.health_monitor = HealthMonitor()
        self.diagnosis_engine = DiagnosisEngine()
        self.recovery_strategies = RecoveryStrategyRegistry()
        self.signature_tracker = SignatureTracker()
    
    async def detect_and_recover(
        self, 
        crawler,
        test_request: Request
    ) -> RecoveryResult:
        """
        检测失效并尝试恢复
        """
        
        # Step 1: 执行测试请求
        try:
            response = await crawler.execute(test_request)
        except Exception as e:
            return await self._handle_error(e, crawler)
        
        # Step 2: 检查响应有效性
        if not self._is_valid_response(response):
            # 签名可能失效
            diagnosis = await self._diagnose_failure(crawler, response)
            
            log.warning("signature_failure_detected",
                      diagnosis=diagnosis.summary)
            
            # Step 3: 尝试恢复
            if diagnosis.can_fix:
                recovery = await self._attempt_recovery(crawler, diagnosis)
                
                # 记录恢复结果用于学习
                self._record_recovery_attempt(diagnosis, recovery)
                
                return recovery
            else:
                return RecoveryResult(
                    success=False,
                    reason=diagnosis.reason,
                    requires_human=True,
                )
        
        # 响应正常：更新签名追踪
        self.signature_tracker.update(test_request, response)
        
        return RecoveryResult(success=True)
    
    async def _diagnose_failure(
        self, 
        crawler, 
        response
    ) -> Diagnosis:
        """
        诊断失败原因
        """
        
        diagnosis = Diagnosis()
        
        # 1. 检查响应状态码
        if response.status in (403, 405):
            diagnosis.add_indicator("http_status", response.status)
            diagnosis.can_fix = True
            diagnosis.recovery_priority = "high"
        
        # 2. 检查响应内容
        if self._is_captcha_page(response):
            diagnosis.add_indicator("captcha", True)
            diagnosis.can_fix = True
            diagnosis.recovery_priority = "high"
        
        # 3. 检查错误消息
        error_msg = self._extract_error_message(response)
        if error_msg:
            diagnosis.add_indicator("error_message", error_msg)
            
            # 尝试匹配已知错误模式
            pattern_match = self.diagnosis_engine.match_pattern(error_msg)
            if pattern_match:
                diagnosis.known_pattern = pattern_match
                diagnosis.suggested_fix = pattern_match.fix
        
        # 4. 检查签名特征
        if self._signature_changed(response):
            diagnosis.add_indicator("signature_changed", True)
            diagnosis.can_fix = True
        
        # 5. 综合判断
        diagnosis.reason = self._summarize_diagnosis(diagnosis)
        
        return diagnosis
    
    async def _attempt_recovery(
        self, 
        crawler, 
        diagnosis: Diagnosis
    ) -> RecoveryResult:
        """
        尝试恢复
        """
        
        strategies = self.recovery_strategies.get_strategies(diagnosis)
        
        for strategy in strategies:
            try:
                log.info("attempting_recovery", 
                        strategy=strategy.name,
                        diagnosis=diagnosis.summary)
                
                result = await strategy.execute(crawler, diagnosis)
                
                if result.success:
                    log.info("recovery_success",
                            strategy=strategy.name)
                    return result
                    
            except Exception as e:
                log.warning("recovery_strategy_failed",
                           strategy=strategy.name,
                           error=str(e))
                continue
        
        return RecoveryResult(
            success=False,
            reason="All recovery strategies failed",
        )
    
    def _is_valid_response(self, response) -> bool:
        """检查响应是否有效"""
        
        if response.status >= 400:
            return False
        
        if self._is_captcha_page(response):
            return False
        
        if self._is_blocked_content(response):
            return False
        
        # 检查数据质量
        if not response.data or len(response.data) == 0:
            return False
        
        return True


class RecoveryStrategyRegistry:
    """恢复策略注册表"""
    
    def __init__(self):
        self._strategies: list[RecoveryStrategy] = [
            RefreshCookiesStrategy(),
            RegenerateSignatureStrategy(),
            RotateProxyStrategy(),
            ResetSessionStrategy(),
            ChangeUserAgentStrategy(),
            WaitAndRetryStrategy(),
        ]
    
    def get_strategies(self, diagnosis: Diagnosis) -> list[RecoveryStrategy]:
        """根据诊断结果获取适当的策略"""
        
        strategies = []
        
        for strategy in self._strategies:
            if strategy.can_handle(diagnosis):
                strategies.append(strategy)
        
        # 按优先级排序
        strategies.sort(key=lambda s: s.priority)
        
        return strategies


class RefreshCookiesStrategy(RecoveryStrategy):
    """刷新Cookie策略"""
    
    name = "refresh_cookies"
    priority = 1
    
    def can_handle(self, diagnosis: Diagnosis) -> bool:
        return "cookie" in diagnosis.indicators or diagnosis.http_status in (403,)
    
    async def execute(self, crawler, diagnosis: Diagnosis) -> RecoveryResult:
        # 重新获取cookie
        await crawler.refresh_cookies()
        
        # 测试
        test_response = await crawler.test_request()
        
        if test_response.status == 200:
            return RecoveryResult(success=True, strategy=self.name)
        
        return RecoveryResult(success=False, reason="Cookie refresh failed")
```

---

## 3. 风控检测能力增强

### 3.1 多维度风控信号检测

```python
class RiskSignalDetector:
    """
    多维度风控信号检测器
    """
    
    def __init__(self):
        self.detectors = {
            "http": HTTPStatusDetector(),
            "timing": TimingAnomalyDetector(),
            "content": ContentPatternDetector(),
            "behavior": BehaviorAnomalyDetector(),
            "device": DeviceFingerprintDetector(),
        }
        self.signal_aggregator = SignalAggregator()
    
    async def scan(
        self, 
        request: Request, 
        response: Response
    ) -> RiskSignalReport:
        """扫描并生成风控信号报告"""
        
        report = RiskSignalReport()
        
        # 并行执行所有检测器
        results = await asyncio.gather(
            self.detectors["http"].detect(request, response),
            self.detectors["timing"].detect(request, response),
            self.detectors["content"].detect(request, response),
            self.detectors["behavior"].detect(request, response),
            self.detectors["device"].detect(request, response),
        ]
        
        # 聚合信号
        for result in results:
            report.add_signals(result.signals)
        
        # 计算综合风险评分
        report.risk_score = self.signal_aggregator.aggregate(report.signals)
        
        return report


class TimingAnomalyDetector:
    """时间异常检测器"""
    
    def detect(self, request, response) -> DetectionResult:
        signals = []
        
        # 1. 检测请求间隔异常
        interval = request.timestamp - request.previous_timestamp
        if interval < 100:  # 小于100ms
            signals.append(Signal(
                type="timing",
                name="request_interval_too_fast",
                severity="medium",
                value=interval,
            ))
        
        # 2. 检测响应时间异常
        if response.response_time > 5000:  # 超过5秒
            signals.append(Signal(
                type="timing",
                name="response_time_slow",
                severity="low",
                value=response.response_time,
            ))
        
        # 3. 检测时间戳异常
        if self._has_timestamp_anomaly(response):
            signals.append(Signal(
                type="timing",
                name="timestamp_anomaly",
                severity="high",
            ))
        
        return DetectionResult(signals=signals)


class ContentPatternDetector:
    """内容模式检测器"""
    
    def __init__(self):
        self.blocked_patterns = self._load_blocked_patterns()
        self.honeypot_keywords = self._load_honeypot_keywords()
    
    def detect(self, request, response) -> DetectionResult:
        signals = []
        
        # 1. 检测拦截页面
        if self._is_blocking_page(response):
            signals.append(Signal(
                type="content",
                name="blocking_page_detected",
                severity="high",
            ))
        
        # 2. 检测蜜罐关键词
        if self._contains_honeypot_content(response):
            signals.append(Signal(
                type="content",
                name="honeypot_content_detected",
                severity="critical",
            ))
        
        # 3. 检测数据异常
        if self._has_data_anomaly(response):
            signals.append(Signal(
                type="content",
                name="data_anomaly",
                severity="medium",
            ))
        
        return DetectionResult(signals=signals)
```

### 3.2 设备指纹强化

```python
class DeviceFingerprint强化器:
    """
    设备指纹强化系统
    """
    
    def __init__(self):
        self.canvas_generator = CanvasFingerprintGenerator()
        self.audio_generator = AudioFingerprintGenerator()
        self.webgl_generator = WebGLFingerprintGenerator()
        self.font_detector = FontDetector()
    
    def generate_fingerprint(self, profile: BrowserProfile) -> DeviceFingerprint:
        """生成完整的设备指纹"""
        
        return DeviceFingerprint(
            # Canvas指纹
            canvas_hash=self.canvas_generator.generate(profile),
            
            # AudioContext指纹
            audio_hash=self.audio_generator.generate(profile),
            
            # WebGL指纹
            webgl_vendor=profile.webgl_vendor,
            webgl_renderer=profile.webgl_renderer,
            
            # 字体列表
            fonts=self.font_detector.detect(profile),
            
            # 时区
            timezone=profile.timezone,
            
            # 屏幕分辨率
            screen_resolution=profile.screen_resolution,
            
            # 平台
            platform=profile.platform,
        )
    
    def make_realistic(self, fingerprint: DeviceFingerprint) -> DeviceFingerprint:
        """让指纹看起来更真实"""
        
        # 添加少量噪声（不改变整体一致性）
        return fingerprint.with_noise(
            noise_level=0.05  # 5%的噪声
        )


class CanvasFingerprintGenerator:
    """Canvas指纹生成器"""
    
    def generate(self, profile: BrowserProfile) -> str:
        """生成Canvas指纹"""
        
        # 创建离屏canvas
        canvas = self._create_canvas()
        
        # 绘制文本（包含Unicode字符以增加复杂性）
        self._draw_text(canvas, profile)
        
        # 绘制图形
        self._draw_shapes(canvas)
        
        # 绘制混合操作
        self._draw_blending(canvas)
        
        # 获取数据URL并计算hash
        data_url = canvas.to_data_url()
        return hashlib.md5(data_url.encode()).hexdigest()
    
    def _create_canvas(self):
        canvas = document.createElement('canvas')
        canvas.width = 280
        canvas.height = 200
        return canvas
```

---

## 4. 自适应学习系统

### 4.1 持续学习架构

```python
class AdaptiveLearningSystem:
    """
    自适应学习系统 - 从实践中持续学习和优化
    """
    
    def __init__(self):
        self.success_patterns = SuccessPatternDatabase()
        self.failure_patterns = FailurePatternDatabase()
        self.strategy_optimizer = StrategyOptimizer()
        self.prediction_model = PredictionModel()
    
    async def learn_from_result(
        self, 
        context: RequestContext,
        result: RequestResult
    ) -> None:
        """从请求结果中学习"""
        
        if result.success:
            await self.success_patterns.record(context, result)
        else:
            await self.failure_patterns.record(context, result)
        
        # 更新策略
        await self.strategy_optimizer.update(context, result)
        
        # 更新预测模型
        await self.prediction_model.update(context, result)
    
    def get_optimized_strategy(
        self, 
        context: RequestContext
    ) -> OptimizedStrategy:
        """根据学习到的知识获取优化后的策略"""
        
        # 从成功模式中获取建议
        success_suggestions = self.success_patterns.get_suggestions(context)
        
        # 从失败模式中获取警告
        failure_warnings = self.failure_patterns.get_warnings(context)
        
        # 从预测模型获取建议
        prediction = self.prediction_model.predict(context)
        
        # 综合所有信息
        strategy = self.strategy_optimizer.optimize(
            success_suggestions=success_suggestions,
            failure_warnings=failure_warnings,
            prediction=prediction,
        )
        
        return strategy


class SuccessPatternDatabase:
    """成功模式数据库"""
    
    def __init__(self):
        self._patterns: list[SuccessPattern] = []
        self._index = PatternIndex()
    
    async def record(self, context: RequestContext, result: RequestResult) -> None:
        """记录成功模式"""
        
        pattern = SuccessPattern(
            domain=context.domain,
            timestamp=time.time(),
            strategy=context.strategy_snapshot,
            response_metrics=result.metrics,
            fingerprint=context.fingerprint_snapshot,
        )
        
        self._patterns.append(pattern)
        self._index.add(pattern)
        
        # 定期清理过期模式
        self._cleanup_old_patterns()
    
    def get_suggestions(self, context: RequestContext) -> list[StrategySuggestion]:
        """获取与当前上下文匹配的成功建议"""
        
        similar = self._index.find_similar(context, limit=5)
        
        suggestions = []
        for pattern in similar:
            suggestions.append(StrategySuggestion(
                source="success_pattern",
                confidence=pattern.confidence,
                recommendations=self._extract_recommendations(pattern),
            ))
        
        return suggestions
    
    def _extract_recommendations(self, pattern: SuccessPattern) -> dict:
        """从成功模式中提取可操作的建议"""
        
        return {
            "request_interval": pattern.avg_interval,
            "user_agent": pattern.user_agent,
            "proxy_rotation": pattern.proxy_rotation_pattern,
            "cookie_refresh": pattern.cookie_refresh_interval,
            "behavior_timing": pattern.behavior_timing,
        }


class FailurePatternDatabase:
    """失败模式数据库"""
    
    def __init__(self):
        self._patterns: list[FailurePattern] = []
        self._failure_classifier = FailureClassifier()
    
    async def record(self, context: RequestContext, result: RequestResult) -> None:
        """记录失败模式"""
        
        classification = self._failure_classifier.classify(result.error)
        
        pattern = FailurePattern(
            domain=context.domain,
            timestamp=time.time(),
            failure_type=classification.type,
            error_details=result.error,
            context_snapshot=context.snapshot(),
        )
        
        self._patterns.append(pattern)
    
    def get_warnings(self, context: RequestContext) -> list[FailureWarning]:
        """获取与当前上下文相关的失败警告"""
        
        # 查找相似的历史失败
        similar_failures = [
            p for p in self._patterns
            if p.domain == context.domain
            and time.time() - p.timestamp < 86400 * 7  # 7天内
        ]
        
        warnings = []
        for failure in similar_failures:
            warnings.append(FailureWarning(
                failure_type=failure.failure_type,
                severity=self._estimate_severity(failure),
                prevention=self._get_prevention(failure),
            ))
        
        return warnings
    
    def _get_prevention(self, failure: FailurePattern) -> str:
        """获取预防建议"""
        
        prevention_map = {
            "signature_expired": "增加cookie刷新频率",
            "rate_limit": "降低请求频率",
            "captcha": "使用更慢的操作节奏",
            "proxy_blocked": "更换代理池",
            "device_fingerprint": "更新设备指纹",
        }
        
        return prevention_map.get(failure.failure_type, "检查请求参数")
```

---

## 5. 实施路线图

### 5.1 阶段一：行为模拟层 (Month 1-2)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 鼠标移动模拟 | 自然轨迹 + 速度变化 | `behavior/mouse_simulator.py` |
| 键盘输入模拟 | 打字节奏 + 错误修正 | `behavior/keyboard_simulator.py` |
| 滚动模式模拟 | 自然滚动 + 停顿 | `behavior/scroll_simulator.py` |
| 空闲模式生成 | 随机等待 + 活动 | `behavior/idle_generator.py` |

### 5.2 阶段二：风控检测层 (Month 2-3)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 蜜罐检测器 | 识别隐藏字段/链接 | `detection/honeypot_detector.py` |
| 请求频率控制 | 自适应请求间隔 | `rate_control/adaptive_limiter.py` |
| 签名失效检测 | 自动检测 + 诊断 | `detection/signature_failure.py` |
| 多维度信号检测 | 综合风险评估 | `detection/risk_signals.py` |

### 5.3 阶段三：设备指纹强化 (Month 3-4)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| Canvas指纹 | 动态生成 | `fingerprint/canvas_generator.py` |
| Audio指纹 | 动态生成 | `fingerprint/audio_generator.py` |
| 字体检测 | 实际字体列表 | `fingerprint/font_detector.py` |
| 指纹一致性 | UA/TLS/WebGL一致 | `fingerprint/coherence_check.py` |

### 5.4 阶段四：自适应学习 (Month 4-5)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 成功模式库 | 从成功中学习 | `learning/success_patterns.py` |
| 失败模式库 | 从失败中学习 | `learning/failure_patterns.py` |
| 策略优化器 | 自动调整策略 | `learning/strategy_optimizer.py` |
| 预测模型 | 预测失败风险 | `learning/prediction_model.py` |

### 5.5 阶段五：自动恢复 (Month 5-6)

| 任务 | 目标 | 交付物 |
|------|------|--------|
| 恢复策略注册 | 多种恢复方案 | `recovery/strategy_registry.py` |
| 自动执行恢复 | 无需人工干预 | `recovery/executor.py` |
| 恢复学习 | 从恢复中优化 | `recovery/learning.py` |

---

## 6. 核心指标

### 6.1 稳定性指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| **30天存活率** | ~40% | >90% | +125% |
| **7天存活率** | ~60% | >95% | +58% |
| **平均无故障运行** | 3天 | >14天 | +367% |
| **自动恢复成功率** | N/A | >70% | 新增 |

### 6.2 风控对抗指标

| 指标 | 当前 | 目标 |
|------|------|------|
| **行为风控检测率** | N/A | <5% |
| **蜜罐误触率** | N/A | <1% |
| **频率风控绕过率** | ~70% | >95% |
| **设备指纹通过率** | ~80% | >95% |

### 6.3 效率指标

| 指标 | 当前 | 目标 |
|------|------|------|
| **人工干预频率** | 每天 | <1次/月 |
| **自动恢复占比** | N/A | >90% |
| **策略调整自动化** | N/A | 100% |

---

## 7. 风险管理

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **行为模拟过度** | 可能被检测为"太真实" | 动态噪声参数 |
| **学习系统过拟合** | 对特定站点有效但不可扩展 | 通用特征提取 |
| **性能开销** | 行为模拟增加延迟 | 异步执行 + 缓存 |
| **维护成本** | 多系统协同复杂 | 模块化 + 自动化测试 |

---

## 8. 成功标准

### 8.1 量化指标

- [ ] 30天存活率 ≥ 90%
- [ ] 平均无故障运行 ≥ 14天
- [ ] 自动恢复成功率 ≥ 70%
- [ ] 人工干预 ≤ 1次/月
- [ ] 行为风控检测率 < 5%

### 8.2 质量指标

- [ ] 完全通用化，无需站点特定配置
- [ ] 自适应学习，无需人工优化
- [ ] 完整自动恢复，无需人工介入
- [ ] 持续进化，越用越强

---

## 9. 技术架构整合

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           整合后的完整系统架构                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        UniversalReverseEngine                            │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │  │
│  │  │ Input Adapter │ │ Data Flow      │ │ Crypto         │              │  │
│  │  │                │ │ Tracker        │ │ Detector       │              │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘              │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │  │
│  │  │ Signature      │ │ AI             │ │ Adaptive       │              │  │
│  │  │ Engine         │ │ Integration    │ │ Learner        │              │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                      ↓                                          │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        RiskControlLayer (新增)                          │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │  │
│  │  │ Behavior       │ │ Honeypot       │ │ Rate           │              │  │
│  │  │ Simulator      │ │ Detector       │ │ Controller     │              │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘              │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │  │
│  │  │ Signature      │ │ Device         │ │ Risk           │              │  │
│  │  │ Failure        │ │ Fingerprint    │ │ Signal         │              │  │
│  │  │ Detector       │ │强化器          │ │ Detector       │              │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                      ↓                                          │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        AutoRecoveryLayer (新增)                          │  │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐              │  │
│  │  │ Strategy      │ │ Recovery       │ │ Learning       │              │  │
│  │  │ Registry      │ │ Executor       │ │ System         │              │  │
│  │  └────────────────┘ └────────────────┘ └────────────────┘              │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

**计划版本**: 1.0  
**创建日期**: 2026-04-07  
**预计完成**: 6 个月  
**状态**: 等待审批
