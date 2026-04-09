# Axelo JS逆向系统 - 全面改进计划 (第三轮)

## 核心理念

> **"不允许任何对特定站点的微调,只允许沉淀到底层的全站点通用系统"**

所有改进必须:
- ✅ 适用于所有站点 (不区分Amazon/Lazada/Shopee/eBay)
- ✅ 沉淀到系统底层 (driver、config、pipeline等)
- ✅ 全站点共享 (一次改进,所有站点受益)

---

## 问题诊断汇总

| 层次 | 问题 | 影响 | 优先级 |
|------|------|------|--------|
| **浏览器层** | 浏览器指纹被识别 | Amazon无法加载页面 | 🔴 严重 |
| **网络层** | 数据中心IP被标记 | 请求被拦截 | 🔴 严重 |
| **行为层** | 机器人行为特征明显 | 被检测为爬虫 | 🟡 中等 |
| **代码层** | 签名逆向失败 | 生成的爬虫无法工作 | 🔴 严重 |
| **流程层** | 验证0%通过 | 无法获取真实数据 | 🔴 严重 |

---

## 改进计划矩阵

### 模块1: 浏览器指纹增强系统

#### 1.1 Canvas指纹随机化

**问题**: 网站通过Canvas渲染检测自动化

**解决方案**:
```python
# axelo/browser/fingerprint/canvas_randomizer.py

class CanvasFingerprintRandomizer:
    """Canvas指纹随机化 - 在浏览器初始化时注入"""
    
    def __init__(self):
        self.noise_modes = ["subtle", "moderate", "aggressive"]
    
    def inject(self, page):
        """向页面注入Canvas噪声"""
        await page.add_init_script("""
            // 随机化Canvas.toDataURL输出
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                // 添加微小的RGB噪声
                const ctx = this.getContext('2d');
                if (ctx) {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    const data = imageData.data;
                    for (let i = 0; i < data.length; i += 4) {
                        data[i] = (data[i] + Math.random() * 2 - 1) | 0;     // R
                        data[i+1] = (data[i+1] + Math.random() * 2 - 1) | 0; // G
                        data[i+2] = (data[i+2] + Math.random() * 2 - 1) | 0; // B
                    }
                    ctx.putImageData(imageData, 0, 0);
                }
                return originalToDataURL.call(this, type);
            };
            
            // 随机化Canvas.toBlob
            const originalToBlob = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toBlob = function(callback, type) {
                // 类似处理...
            };
        """)
```

**效果**: 每个Canvas渲染都有微小随机噪声,难以被检测

---

#### 1.2 AudioContext指纹伪装

**问题**: 网站通过AudioContext检测自动化工具

**解决方案**:
```python
# axelo/browser/fingerprint/audio_randomizer.py

class AudioFingerprintRandomizer:
    """AudioContext指纹伪装"""
    
    def inject(self, page):
        await page.add_init_script("""
            // 模拟真实音频处理
            const originalCreateBuffer = AudioContext.prototype.createBuffer;
            AudioContext.prototype.createBuffer = function(channels, length, sampleRate) {
                const buffer = originalCreateBuffer.call(this, channels, length, sampleRate);
                // 添加微小的随机偏移
                const data = buffer.getChannelData(0);
                for (let i = 0; i < data.length; i += 100) {
                    data[i] += (Math.random() - 0.5) * 0.0001;
                }
                return buffer;
            };
        """)
```

---

#### 1.3 WebGL指纹伪装

**问题**: 网站通过WebGL vendor/renderer检测

**解决方案**:
```python
# axelo/browser/fingerprint/webgl_randomizer.py

class WebGLFingerprintRandomizer:
    """WebGL指纹伪装"""
    
    VENDORS = [
        "NVIDIA GeForce RTX 3080/PCIe/SSE2",
        "AMD Radeon RX 6800 XT",
        "Intel Iris OpenGL Renderer",
    ]
    
    def inject(self, page):
        vendor = random.choice(self.VENDORS)
        await page.add_init_script(f"""
            const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) return "{vendor.split('/')[0]}";
                if (parameter === 37446) return "{vendor.split('/')[1]}";
                return originalGetParameter.call(this, parameter);
            }};
        """)
```

---

#### 1.4 完整指纹注入系统

```python
# axelo/browser/fingerprint/injector.py

class FingerprintInjector:
    """统一指纹注入系统"""
    
    def __init__(self):
        self.canvas = CanvasFingerprintRandomizer()
        self.audio = AudioFingerprintRandomizer()
        self.webgl = WebGLFingerprintRandomizer()
    
    async def inject_all(self, page):
        """注入所有指纹伪装"""
        await self.canvas.inject(page)
        await self.audio.inject(page)
        await self.webgl.inject(page)
        # 添加更多...
```

---

### 模块2: 代理与IP轮换系统

#### 2.1 代理配置管理

**问题**: 数据中心IP被Amazon等站点标记

**解决方案**:
```python
# axelo/network/proxy_manager.py

class ProxyManager:
    """代理管理器"""
    
    def __init__(self):
        self.proxies: list[ProxyConfig] = []
        self.current_index = 0
        self.failure_count = {}
    
    def add_proxy(self, proxy_url: str, proxy_type: str = "http"):
        """添加代理"""
        self.proxies.append(ProxyConfig(
            url=proxy_url,
            type=proxy_type,
            max_failures=3,
        ))
    
    def get_next_proxy(self) -> ProxyConfig:
        """获取下一个可用代理 (轮换)"""
        # 跳过连续失败的代理
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self.current_index]
            if self.failure_count.get(proxy.url, 0) < proxy.max_failures:
                return proxy
            self.current_index = (self.current_index + 1) % len(self.proxies)
        return self.proxies[self.current_index]
    
    def mark_failure(self, proxy_url: str):
        """标记代理失败"""
        self.failure_count[proxy_url] = self.failure_count.get(proxy_url, 0) + 1
```

---

#### 2.2 代理配置扩展

```python
# axelo/config.py 新增配置

# 代理配置
proxy_rotation_enabled: bool = True  # 启用代理轮换
proxy_max_retries: int = 3  # 每个代理最大重试次数
proxy_urls: list[str] = []  # 代理URL列表
proxy_rotation_strategy: str = "round_robin"  # 轮换策略

# 住宅代理预设 (可选)
residential_proxy_services: list[str] = [
    "bright_data",  # Bright Data
    "oxylabs",      # Oxylabs
    "smartproxy",   # Smartproxy
]
```

---

### 模块3: 行为模拟系统

#### 3.1 真实浏览轨迹模拟

**问题**: 机器人直接访问目标URL,行为不自然

**解决方案**:
```python
# axelo/behavior/trajectory_simulator.py

class TrajectorySimulator:
    """浏览轨迹模拟器 - 模拟真实用户行为"""
    
    async def simulate_user_journey(self, page, target_url: str):
        """模拟用户浏览轨迹"""
        # 1. 先访问搜索引擎或无关网站
        await page.goto("https://www.google.com/search?q=laptop")
        await self._random_wait(2, 5)
        
        # 2. 随机滚动
        await self._random_scroll(page)
        await self._random_wait(1, 3)
        
        # 3. 点击搜索结果进入目标
        await page.click("a >> nth=0")
        await self._random_wait(3, 8)
        
        # 4. 在目标页面浏览
        await self._random_scroll(page)
        await self._mouse_movements(page)
        await self._random_wait(2, 5)
    
    async def _random_scroll(self, page):
        """随机滚动"""
        for _ in range(random.randint(2, 5)):
            await page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    async def _mouse_movements(self, page):
        """随机鼠标移动"""
        for _ in range(random.randint(3, 8)):
            x = random.randint(100, 1000)
            y = random.randint(100, 800)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.5))
    
    def _random_wait(self, min_sec: float, max_sec: float):
        """随机等待"""
        return asyncio.sleep(random.uniform(min_sec, max_sec))
```

---

#### 3.2 请求间隔随机化

**问题**: 固定间隔请求被识别为机器人

**解决方案**:
```python
# axelo/network/request_pacer.py

class RequestPacer:
    """请求间隔控制器"""
    
    def __init__(self):
        self.min_interval = 1.0  # 最小间隔(秒)
        self.max_interval = 5.0  # 最大间隔(秒)
        self.jitter = 0.3  # 抖动系数
    
    async def wait_before_request(self):
        """请求前等待"""
        base = random.uniform(self.min_interval, self.max_interval)
        jitter_amount = base * self.jitter * random.uniform(-1, 1)
        await asyncio.sleep(base + jitter_amount)
    
    def set_interval(self, min_sec: float, max_sec: float):
        """设置间隔范围"""
        self.min_interval = min_sec
        self.max_interval = max_sec
```

---

### 模块4: Cookie预获取系统

#### 4.1 Cookie池管理

**问题**: 没有有效Cookie,一访问就被拦截

**解决方案**:
```python
# axelo/browser/cookie_pool.py

class CookiePool:
    """Cookie池管理器"""
    
    def __init__(self):
        self.cookies: dict[str, list[dict]] = {}  # domain -> cookies
    
    def add_cookies(self, domain: str, cookies: list[dict]):
        """添加Cookie"""
        self.cookies[domain] = cookies
    
    async def get_valid_cookie(self, domain: str) -> list[dict] | None:
        """获取有效Cookie"""
        cookies = self.cookies.get(domain, [])
        # 检查是否过期
        valid = [c for c in cookies if self._is_valid(c)]
        return valid[0] if valid else None
    
    def _is_valid(self, cookie: dict) -> bool:
        """检查Cookie是否有效"""
        if "expires" not in cookie:
            return True
        # 检查是否过期...
        return True
    
    async def fetch_fresh_cookies(self, domain: str) -> list[dict]:
        """获取新Cookie (使用curl_cffi)"""
        # 使用curl_cffi获取Cookie,不需要浏览器
        import curl_cffi
        session = curl_cffi.Session(impersonate="chrome")
        response = session.get(f"https://{domain}")
        return session.cookies.get_dict()
```

---

### 模块5: HTTP降级方案

#### 5.1 浏览器失败时的备选方案

**问题**: 浏览器完全无法加载页面时,没有备选

**解决方案**:
```python
# axelo/pipeline/fallback/http_fallback.py

class HTTPFallback:
    """HTTP降级方案 - 当浏览器失败时使用"""
    
    def __init__(self):
        self.session = curl_cffi.Session(impersonate="chrome")
    
    async def analyze_api(self, api_url: str, method: str = "GET") -> dict:
        """直接分析API,不需要浏览器"""
        # 1. 发送请求
        if method == "GET":
            response = self.session.get(api_url)
        else:
            response = self.session.post(api_url)
        
        # 2. 分析响应
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body_sample": response.text[:1000],
            "content_type": response.headers.get("content-type", ""),
        }
    
    async def extract_signature_hints(self, response_text: str) -> list[str]:
        """从响应中提取签名线索"""
        # 分析响应,找出可能的签名字段
        hints = []
        # 查找时间戳
        if "timestamp" in response_text.lower():
            hints.append("timestamp")
        # 查找签名字段
        if "sign" in response_text.lower():
            hints.append("sign")
        return hints
```

---

### 模块6: 签名逆向增强系统

#### 6.1 静态分析增强

**问题**: 静态分析找到太多无用的候选

**解决方案**:
```python
# axelo/analysis/static/enhanced_analyzer.py

class EnhancedStaticAnalyzer:
    """增强的静态分析器"""
    
    def __init__(self):
        self.weighted_patterns = {
            "crypto": {
                "HMAC": 3.0,
                "SHA256": 2.5,
                "MD5": 2.0,
                "AES": 2.5,
            },
            "network": {
                "fetch": 1.5,
                "XMLHttpRequest": 1.5,
                "axios": 1.8,
            },
            "encoding": {
                "btoa": 1.2,
                "atob": 1.2,
                "encodeURIComponent": 1.0,
            }
        }
    
    def analyze_with_weights(self, bundle_content: str) -> list[Candidate]:
        """带权重的分析"""
        candidates = []
        
        for category, patterns in self.weighted_patterns.items():
            for pattern, weight in patterns.items():
                matches = self._find_pattern(bundle_content, pattern)
                for match in matches:
                    candidate = Candidate(
                        pattern=pattern,
                        weight=weight,
                        location=match.location,
                        context=match.context,
                    )
                    candidates.append(candidate)
        
        # 按权重排序
        return sorted(candidates, key=lambda c: c.weight, reverse=True)
    
    def filter_by_context(self, candidates: list[Candidate], api_url: str) -> list[Candidate]:
        """根据API URL上下文过滤候选"""
        # 只保留与API调用相关的候选
        # ...
        return candidates
```

---

#### 6.2 AI分析增强

```python
# axelo/ai/enhanced_hypothesis.py

class EnhancedHypothesisAgent:
    """增强的假设生成器"""
    
    async def analyze_with_multiple_strategies(
        self,
        static_results: dict,
        dynamic_results: dict | None,
        api_endpoint: str,
    ) -> AIHypothesis:
        """使用多种策略分析"""
        
        # 策略1: 如果有动态结果,优先使用
        if dynamic_results and len(dynamic_results) > 0:
            return await self._analyze_dynamic_first(dynamic_results, api_endpoint)
        
        # 策略2: 如果静态结果丰富,使用深度分析
        elif static_results and len(static_results) > 50:
            return await self._analyze_static_deep(static_results, api_endpoint)
        
        # 策略3: 如果结果少,使用启发式
        else:
            return await self._analyze_heuristic(static_results, api_endpoint)
```

---

### 模块7: 验证率提升系统

#### 7.1 自适应验证

**问题**: 验证0%通过,不知道哪里出错

**解决方案**:
```python
# axelo/verification/adaptive_verifier.py

class AdaptiveVerifier:
    """自适应验证器"""
    
    def __init__(self):
        self.strategies = [
            "json_path_variants",
            "header_fallback",
            "param_variants",
            "retry_with_ua",
        ]
    
    async def verify_with_adaptive_path(
        self,
        crawler_code: str,
        api_endpoint: str,
    ) -> VerificationResult:
        """自适应验证,尝试多种路径"""
        
        results = []
        
        # 策略1: 尝试不同的JSON路径
        json_paths = self._extract_json_paths(crawler_code)
        for path in json_paths:
            result = await self._try_verify(api_endpoint, path)
            results.append(result)
            if result.success:
                return result
        
        # 策略2: 尝试不同的Header
        for ua in ["chrome", "firefox", "safari"]:
            result = await self._try_verify_with_ua(api_endpoint, ua)
            results.append(result)
            if result.success:
                return result
        
        # 返回最佳结果
        return max(results, key=lambda r: r.data_quality)
    
    def _extract_json_paths(self, code: str) -> list[str]:
        """从爬虫代码中提取可能的JSON路径"""
        # 解析代码,找出可能的路径...
        return ["$.data.items", "$.items", "$.results", "$.products"]
```

---

### 模块8: 代码质量保证

#### 8.1 错误处理增强

```python
# axelo/pipeline/error_handler.py

class PipelineErrorHandler:
    """Pipeline错误处理器"""
    
    def __init__(self):
        self.error_log = []
    
    async def handle_stage_error(
        self,
        stage_name: str,
        error: Exception,
        context: dict,
    ) -> ErrorResolution:
        """处理各阶段的错误"""
        
        # 记录错误
        self.error_log.append({
            "stage": stage_name,
            "error": str(error),
            "context": context,
            "timestamp": datetime.now(),
        })
        
        # 根据错误类型决定处理方式
        if self._is_retryable(error):
            return ErrorResolution(action="retry", max_attempts=3)
        elif self._is_fallback_available(error):
            return ErrorResolution(action="fallback", fallback_strategy=self._get_fallback(stage_name))
        else:
            return ErrorResolution(action="skip", reason="unrecoverable")
    
    def _is_retryable(self, error: Exception) -> bool:
        """检查错误是否可重试"""
        retryable_types = [TimeoutError, ConnectionError]
        return any(isinstance(error, t) for t in retryable_types)
```

---

## 实施优先级与时间规划

### Phase 1: 核心修复 (1-2天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 1.1 | 完善错误处理 | 任何stage失败不中断 |
| 1.2 | 统一超时配置 | 避免配置混乱 |
| 1.3 | 增强容错 | 优雅降级 |

### Phase 2: 浏览器指纹 (3-5天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 2.1 | Canvas指纹随机化 | 绕过Canvas检测 |
| 2.2 | AudioContext伪装 | 绕过音频指纹 |
| 2.3 | WebGL指纹伪装 | 绕过WebGL检测 |
| 2.4 | 统一注入系统 | 一行代码注入所有 |

### Phase 3: 代理系统 (2-3天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 3.1 | 代理管理器 | 支持轮换 |
| 3.2 | 代理配置 | 可配置多个代理 |
| 3.3 | 失败切换 | 自动跳过失败代理 |

### Phase 4: 行为模拟 (3-5天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 4.1 | 浏览轨迹模拟 | 更像真实用户 |
| 4.2 | 请求间隔随机化 | 避免固定模式 |
| 4.3 | 鼠标/滚动模拟 | 自然交互 |

### Phase 5: Cookie与HTTP降级 (2-3天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 5.1 | Cookie池管理 | 复用有效Cookie |
| 5.2 | HTTP降级 | 浏览器失败时备用 |

### Phase 6: 签名逆向增强 (5-7天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 6.1 | 权重分析 | 更准确的候选 |
| 6.2 | 多策略AI | 根据情况选择方法 |
| 6.3 | 上下文过滤 | 排除无关候选 |

### Phase 7: 验证率提升 (3-5天)

| 任务 | 描述 | 预期效果 |
|------|------|----------|
| 7.1 | 自适应验证 | 尝试多种路径 |
| 7.2 | 错误诊断 | 快速定位问题 |
| 7.3 | 自动修复 | 尝试修复常见问题 |

---

## 文件修改清单

### 新增文件

| 文件路径 | 描述 |
|----------|------|
| `axelo/browser/fingerprint/__init__.py` | 指纹模块入口 |
| `axelo/browser/fingerprint/canvas_randomizer.py` | Canvas指纹 |
| `axelo/browser/fingerprint/audio_randomizer.py` | Audio指纹 |
| `axelo/browser/fingerprint/webgl_randomizer.py` | WebGL指纹 |
| `axelo/browser/fingerprint/injector.py` | 统一注入器 |
| `axelo/network/proxy_manager.py` | 代理管理器 |
| `axelo/network/request_pacer.py` | 请求间隔控制 |
| `axelo/behavior/trajectory_simulator.py` | 轨迹模拟器 |
| `axelo/browser/cookie_pool.py` | Cookie池 |
| `axelo/pipeline/fallback/http_fallback.py` | HTTP降级 |
| `axelo/pipeline/error_handler.py` | 错误处理 |
| `axelo/verification/adaptive_verifier.py` | 自适应验证 |

### 修改文件

| 文件 | 修改 |
|------|------|
| `axelo/config.py` | 添加代理、指纹等配置 |
| `axelo/browser/driver.py` | 集成指纹注入 |
| `axelo/browser/enhanced_driver.py` | 同步更新 |
| `axelo/pipeline/stages/s5_dynamic.py` | 添加降级逻辑 |
| `axelo/ai/enhanced_hypothesis.py` | 多策略分析 |
| `axelo/analysis/static/enhanced_analyzer.py` | 权重分析 |

---

## 验收标准

### 短期 (Phase 1-2)
- [ ] 错误不中断流程
- [ ] 超时配置统一
- [ ] 至少3个站点完成流程

### 中期 (Phase 3-5)
- [ ] Amazon页面可以加载
- [ ] 代理轮换工作
- [ ] 行为更自然

### 长期 (Phase 6-7)
- [ ] 验证通过率 > 30%
- [ ] 签名逆向更准确
- [ ] 自动错误修复

---

## 总结

这个计划涵盖了:
1. **8个核心模块** - 从浏览器到AI分析
2. **20+个文件** - 新增和修改
3. **7个Phase** - 分阶段实施
4. **全站点通用** - 无站点特定代码

所有改进都:
- ✅ 适用于所有站点
- ✅ 沉淀到系统底层
- ✅ 全站点共享

---

**请审核此计划,确认后我将开始实施。**