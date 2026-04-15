# Axelo 系统问题解决方案

## 一、核心问题优先级

| 优先级 | 问题 | 当前状态 | 目标 |
|--------|------|----------|------|
| 🔴 P0 | 验证是假的 | 仅静态检查 | 实际运行验证 |
| 🔴 P0 | 代码是模板 | 密钥占位符 | 自动提取密钥 |
| 🟡 P1 | AI分析浅 | 静态正则 | 动态执行 |
| 🟡 P1 | 数据流脆弱 | 硬编码fallback | Schema验证 |
| 🟡 P1 | trace未定义 | 运行时可能报错 | 修复常量引用 |
| 🟡 P2 | Stealth弱 | 31向量 | 60+向量 |
| 🟡 P2 | Storage并发 | 无锁 | 原子写入 |

---

## 二、详细解决方案

### P0-1: 真正验证 (verify_tool.py)

**问题**: 当前只做静态语法检查，不实际运行代码

**解决方案**:

```python
# axelo/tools/verify_tool.py 改进方案

class VerifyTool(BaseTool):
    async def execute(self, input_data: dict, state: ToolState) -> ToolResult:
        # 1. 保留原有语法检查
        errors, warnings = self._syntax_check(code)
        
        # 2. 新增: 实际运行验证
        if not errors:
            execution_result = await self._run_actual_test(code, target_url)
            
            # 3. 检查是否被反爬拦截
            if execution_result.is_blocked:
                errors.append(f"反爬拦截: {execution_result.block_reason}")
                warnings.append("建议: 检查UA/cookies/签名是否正确")
            
            # 4. 检查返回数据是否有效
            if not execution_result.has_valid_data:
                errors.append("返回数据为空或格式错误")
            
            # 5. 运行签名测试 (如果有签名函数)
            if "generate_signature" in code:
                sig_result = await self._test_signature(code)
                if not sig_result.success:
                    warnings.append(f"签名测试失败: {sig_result.error}")
        
        # ... 原有逻辑
```

**关键依赖**:
- 需要调用 `verification/engine.py` 的 `VerificationEngine`
- 需要 `replayer.py` 来实际运行爬虫
- 需要 `antibot_detector.py` 来检测拦截

---

### P0-2: 动态签名提取 (codegen_tool.py)

**问题**: 永远生成占位符 `SECRET_KEY = "YOUR_SECRET_KEY_HERE"`

**解决方案 - 三层密钥提取**:

```python
# axelo/tools/signature_extractor.py (新建)

class SignatureExtractor:
    """从JS中提取真实签名逻辑"""
    
    async def extract(self, js_code: str, api_calls: list) -> dict:
        result = {
            "key_source": None,  # hardcoded/api/computed
            "key_value": None,
            "algorithm": None,
            "param_format": None,
        }
        
        # Layer 1: 硬编码密钥
        hardcoded = self._find_hardcoded_key(js_code)
        if hardcoded:
            result.update(hardcoded)
            return result
        
        # Layer 2: API获取密钥
        api_key = await self._find_api_key(js_code, api_calls)
        if api_key:
            result.update(api_key)
            return result
        
        # Layer 3: 计算密钥 (最复杂)
        computed = self._analyze_key_computation(js_code)
        if computed:
            result.update(computed)
            return result
        
        return result  # 找不到时返回None，让codegen用占位符
    
    def _find_hardcoded_key(self, js_code: str) -> dict:
        """查找硬编码密钥"""
        patterns = [
            r'(?:key|secret|token|apiKey)\s*[:=]\s*["\']([a-zA-Z0-9]{16,})["\']',
            r'CryptoJS\.enc\.Utf8\.parse\(["\']([a-zA-Z0-9]{16,})["\']',
        ]
        # ... 返回找到的密钥
```

**Codegen集成**:

```python
# axelo/tools/codegen_tool.py 改进

def _generate(self, input_data: dict) -> CodegenOutput:
    # ... 原有逻辑
    
    # 新增: 尝试提取真实密钥
    extractor = SignatureExtractor()
    sig_info = await extractor.extract(
        js_code=input_data.get("js_code", ""),
        api_calls=input_data.get("api_endpoints", [])
    )
    
    if sig_info.get("key_value"):
        # 用真实密钥替换占位符
        output.python_code = output.python_code.replace(
            'SECRET_KEY = "YOUR_SECRET_KEY_HERE"',
            f'SECRET_KEY = "{sig_info["key_value"]}"'
        )
```

---

### P1-1: 动态执行JS (ai_tool.py)

**问题**: 只用静态分析，AI只能猜测

**解决方案**:

```python
# axelo/tools/dynamic_analyzer.py (新建)

class DynamicAnalyzer:
    """动态执行JS观察真实行为"""
    
    async def analyze(self, page, target_function: str) -> dict:
        # 1. 设置断点或拦截
        await page.evaluate("""
            window.__axelo_traces = [];
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                window.__axelo_traces.push({
                    type: 'fetch',
                    url: args[0],
                    options: args[1]
                });
                return originalFetch.apply(this, args);
            };
        """)
        
        # 2. 触发目标函数
        await page.evaluate(f"{target_function}()")
        
        # 3. 收集调用痕迹
        traces = await page.evaluate("window.__axelo_traces")
        
        # 4. 分析签名生成逻辑
        return self._analyze_traces(traces)
```

**AI Tool集成**:

```python
# axelo/tools/ai_tool.py 改进

async def _generate_analysis(self, input_data, state) -> AIAnalysisOutput:
    # ... 原有静态分析
    
    # 新增: 动态执行 (如果有browser context)
    if state.context.get("page"):  # Playwright page对象
        dynamic_result = await DynamicAnalyzer().analyze(
            page=state.context["page"],
            target_function="sign"  # 从静态分析推断的函数名
        )
        
        # 合并动态结果到输出
        if dynamic_result.get("actual_params"):
            output.actual_signature_params = dynamic_result["actual_params"]
            output.confidence = min(output.confidence + 0.2, 1.0)  # 提高置信度
    
    return output
```

---

### P1-2: Schema验证 (executor.py)

**问题**: 工具输出格式变化导致崩溃

**解决方案**:

```python
# axelo/tools/base.py 增强

from pydantic import BaseModel, validator
from typing import Any

class ToolOutputSchema(BaseModel):
    """工具输出Schema验证"""
    
    @validator("*", pre=True, always=True)
    def convert_none(cls, v):
        if v is None:
            return {}
        return v

class BaseTool(BaseTool):
    def _validate_output(self, output: dict, expected_schema: list) -> dict:
        """验证输出符合schema"""
        validated = {}
        for field in expected_schema:
            name = field.name
            if name in output:
                validated[name] = output[name]
            elif field.required:
                # 字段缺失但非必需: 警告
                log.warning(f"Tool {self.name} missing required field: {name}")
            else:
                validated[name] = field.default
        
        return validated
    
    async def run(self, input_data: dict, state: ToolState) -> ToolResult:
        # ... 执行逻辑
        
        # 新增: 输出验证
        output = self._validate_output(raw_output, self._create_schema().output_schema)
        
        return ToolResult(..., output=output)
```

---

### P1-3: 修复trace_tool.py未定义常量

**问题**: `self.SIGNATURE_PATTERNS` 和 `self.CRYPTO_FUNCTIONS` 未定义

**解决方案**:

```python
# axelo/tools/trace_tool.py 修复

class TraceTool(BaseTool):
    # 定义类常量 (不要放在__init__里)
    SIGNATURE_PATTERNS = [
        r"sign\w*\s*\(",
        r"signature\w*\s*\(",
        r"generate\w*Signature\w*\s*\(",
    ]
    
    CRYPTO_FUNCTIONS = [
        "CryptoJS.HMAC",
        "CryptoJS.AES",
        "crypto.subtle.sign",
        "window.crypto.subtle",
    ]
    
    def __init__(self):
        super().__init__()
        # 不要重新定义这些常量
    
    # 使用 self.SIGNATURE_PATTERNS 或 TraceTool.SIGNATURE_PATTERNS
    def _static_trace(self, js_code: str) -> dict:
        for pattern in self.SIGNATURE_PATTERNS:  # 正确
            # ...
```

---

### P2-1: 增强Stealth配置

**问题**: 只有31个检测向量

**解决方案**:

```python
# axelo/tools/stealth_config.py 增强

def get_all_stealth_scripts(locale: str = None) -> str:
    # 原有31个向量...
    
    # 新增向量:
    new_scripts = """
    // ==== Canvas 指纹随机化 ====
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.drawImage(this, 0, 0);
        // 添加随机噪声
        ctx.fillStyle = Math.random() > 0.5 ? '#fff' : '#000';
        ctx.fillRect(0, 0, 1, 1);
        return originalToDataURL.call(this, type);
    };
    
    // ==== WebGL 指纹随机化 ====
    const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) {
            return 'Intel Inc.'; // 始终返回假vendor
        }
        if (parameter === 37446) {
            return 'Intel Iris OpenGL Engine'; // 假renderer
        }
        return originalGetParameter.call(this, parameter);
    };
    
    // ==== AudioContext 指纹随机化 ====
    const originalCreateAnalyser = AudioContext.prototype.createAnalyser;
    AudioContext.prototype.createAnalyser = function() {
        const analyser = originalCreateAnalyser.call(this);
        // 伪造fftSize
        Object.defineProperty(analyser, 'fftSize', {
            get: () => 2048,
            set: () => {}
        });
        return analyser;
    };
    
    // ==== 字体枚举防护 ====
    const originalGetComputedStyle = window.getComputedStyle;
    window.getComputedStyle = function(element) {
        const style = originalGetComputedStyle.call(this, element);
        // 随机化 font-family
        if (style.fontFamily) {
            const fonts = style.fontFamily.split(',');
            if (fonts.length > 1) {
                // 随机打乱字体顺序
                style.fontFamily = fonts.sort(() => Math.random() - 0.5).join(',');
            }
        }
        return style;
    };
    
    // ==== 硬件并发伪造 ====
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => navigator.hardwareConcurrency || 8,
    });
    
    // ==== 电池API伪造 ====
    if (navigator.getBattery) {
        navigator.getBattery = async () => ({
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1.0,
        });
    }
    """
    
    return existing_scripts + new_scripts
```

---

### P2-2: Storage原子写入

**问题**: 多进程写同一JSON可能损坏

**解决方案**:

```python
# axelo/storage/atomic_writer.py (新建)

import tempfile
import os
import json
from pathlib import Path

class AtomicWriter:
    """原子写入工具"""
    
    @staticmethod
    def write_json(path: Path, data: dict) -> None:
        """原子写入JSON"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. 写入临时文件
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=".tmp_",
            suffix=".json"
        )
        
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # 强制刷盘
            
            # 2. 原子重命名
            os.replace(temp_path, path)
            
        except Exception:
            # 3. 失败时清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    @staticmethod
    def read_json(path: Path) -> dict | None:
        """安全读取JSON"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return None

# 使用示例
# 替换原有 write_text 调用
AtomicWriter.write_json(session_dir / "state.json", state_dict)
```

---

## 三、实施路线图

### Phase 1: 关键修复 (1-2周)
1. ✅ 修复 trace_tool.py 未定义常量
2. ✅ 添加 verify_tool 实际运行验证
3. ✅ 修复 deobfuscate_tool.py 结构问题

### Phase 2: 核心增强 (2-3周)
4. 实现 SignatureExtractor 密钥提取
5. 集成动态执行JS分析
6. 添加 Schema 验证

### Phase 3: 全面增强 (3-4周)
7. 增强 Stealth 到 60+ 向量
8. 添加 Storage 原子写入
9. 完善错误处理和日志

---

## 四、验证清单

完成解决方案后，验证:

- [ ] verify_tool 实际运行代码并检查反爬拦截
- [ ] codegen 生成包含真实密钥的代码 (或明确说明无法提取)
- [ ] ai_analyze 能获取动态执行结果
- [ ] executor 对工具输出做 Schema 验证
- [ ] trace_tool 不再报未定义错误
- [ ] Stealth 能绕过至少 60 个检测向量
- [ ] Storage 在并发场景下不损坏

---

## 五、风险与依赖

| 任务 | 依赖 | 风险 |
|------|------|------|
| 真正验证 | verification/engine.py | 需要 Playwright |
| 密钥提取 | 静态/动态分析 | 可能找不到密钥 |
| 动态JS | Playwright page | 需要browser context |
| Stealth增强 | 无 | 可能被检测 |
| 原子写入 | 无 | 跨平台兼容性 |

---

*方案版本: 2026-04-10*