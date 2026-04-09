# 免费模型协作架构计划书

## 1. 战略愿景

### 1.1 核心目标

构建一个**低成本、高效率**的逆向推理架构：

- **双模型协作**：推理模型 + 编程模型分工合作
- **免费优先**：使用 DeepSeek R1 (推理) + Qwen3-Coder (编程)
- **失败回退**：免费模型失败时自动调用 Claude
- **成本优化**：日常任务零成本，只在失败时消耗 Claude

### 1.2 模型选择

| 用途 | 模型 | 特点 | 费用 |
|------|------|------|------|
| **推理** | DeepSeek R1 | 深度思考、Chain-of-Thought | 免费 (API) |
| **编程** | Qwen3-Coder | 代码生成、调试、修复 | 免费 (API) |
| **回退** | Claude | 高质量、复杂问题处理 | 按需付费 |

---

## 2. 技术架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Dual-Model Collaboration Architecture                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                          Task Input                                     │   │
│   │                    (JavaScript 分析请求)                                 │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                           │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      Task Router                                         │   │
│   │              (判断任务类型: 推理型 / 编程型 / 混合型)                     │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                           │
│   ┌───────────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │      Reasoning Model (DeepSeek)   │   │    Coding Model (Qwen3-Coder)    │ │
│   │  ┌─────────────────────────────┐ │   │  ┌─────────────────────────────┐ │ │
│   │  │ • 分析加密逻辑              │ │   │  │ • 生成签名代码              │ │ │
│   │  │ • 识别算法类型              │ │   │  │ • 调试错误                 │ │ │
│   │  │ • 追踪数据流               │ │   │  │ • 修复代码问题             │ │ │
│   │  │ • 推导签名规则              │ │   │  │ • 优化实现                 │ │ │
│   │  └─────────────────────────────┘ │   │  └─────────────────────────────┘ │ │
│   │              ↓                  │   │              ↓                    │ │
│   └───────────────────────────────────┘   └───────────────────────────────────┘ │
│                    ↓                              ↓                            │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                     Result Aggregator                                    │   │
│   │            (合并推理结果 + 代码结果 = 完整解决方案)                        │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                           │
│   ┌─────────────────────────────┐    ┌─────────────────────────────────────┐  │
│   │        Validation            │    │        Fallback to Claude           │  │
│   │   (验证代码是否正确运行)       │    │   (失败时触发，调用 Claude API)     │  │
│   └─────────────────────────────┘    └─────────────────────────────────────┘  │
│            ↓                                      ↓                            │
│   ┌───────────────────────────────────┐   ┌───────────────────────────────────┐ │
│   │         Success ✓                 │   │         Claude Retry              │ │
│   │      (低成本完成)                 │   │      (使用 Claude 重新处理)        │ │
│   └───────────────────────────────────┘   └───────────────────────────────────┘ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 详细工作流程

```python
class DualModelOrchestrator:
    """
    双模型协作编排器
    
    工作流程:
    1. 接收任务
    2. 分析任务类型
    3. DeepSeek R1 进行推理分析
    4. Qwen3-Coder 基于推理结果生成代码
    5. 验证代码
    6. 成功 → 返回结果
    7. 失败 → 回退到 Claude
    """
    
    def __init__(self):
        # 模型客户端
        self.reasoning_client = DeepSeekClient()      # DeepSeek R1
        self.coding_client = QwenClient()             # Qwen3-Coder
        self.claude_client = ClaudeClient()            # Claude (备用)
        
        # 配置
        self.config = {
            "max_retries": 2,
            "timeout": 60,
            "fallback_on_error": True,
        }
    
    async def execute(self, task: Task) -> ExecutionResult:
        """执行任务"""
        
        # Step 1: 分析任务类型
        task_type = self._classify_task(task)
        
        # Step 2: 并行调用两个模型 (如果是混合型)
        if task_type == "hybrid":
            # 并行执行推理和编码
            reasoning_result, coding_result = await asyncio.gather(
                self._run_reasoning(task),
                self._run_coding(task),
            )
            
            # 合并结果
            result = self._merge_results(reasoning_result, coding_result)
        
        elif task_type == "reasoning_only":
            result = await self._run_reasoning(task)
        
        elif task_type == "coding_only":
            result = await self._run_coding(task)
        
        # Step 3: 验证结果
        if not self._validate(result):
            # Step 4: 回退到 Claude
            return await self._fallback_to_claude(task)
        
        return result
    
    async def _run_reasoning(self, task: Task) -> ReasoningResult:
        """运行推理模型"""
        
        prompt = f"""
        你是一个专业的逆向工程师。请分析以下 JavaScript 代码：
        
        {task.js_code}
        
        请提供:
        1. 签名生成逻辑分析
        2. 使用的加密算法
        3. 关键函数和数据流
        4. 签名参数位置
        """
        
        response = await self.reasoning_client.chat(prompt)
        
        return ReasoningResult(
            analysis=response.content,
            confidence=response.confidence,
            algorithm=response.algorithm,
        )
    
    async def _run_coding(self, task: Task) -> CodingResult:
        """运行编程模型"""
        
        prompt = f"""
        基于以下分析结果，生成 Python 签名生成代码：
        
        分析: {task.reasoning_result.analysis}
        算法: {task.reasoning_result.algorithm}
        
        请生成完整、可运行的签名生成代码。
        """
        
        response = await self.coding_client.chat(prompt)
        
        return CodingResult(
            code=response.code,
            language="python",
        )
    
    async def _fallback_to_claude(self, task: Task) -> ExecutionResult:
        """回退到 Claude"""
        
        prompt = f"""
        之前的免费模型未能成功处理此任务。请重新分析并生成代码。
        
        原始 JavaScript:
        {task.js_code}
        
        任务目标: {task.goal}
        
        请提供完整的分析和代码。
        """
        
        response = await self.claude_client.chat(prompt)
        
        return ExecutionResult(
            success=True,
            code=response.code,
            source="claude",
            fallback=True,
        )
```

### 2.3 模型对比

#### DeepSeek R1 (推理模型)

```python
# 优势:
# - 深度推理能力 (Chain-of-Thought)
# - 数学和逻辑分析强
# - 免费 API
# - 支持长上下文

# 适用场景:
# - 分析 JavaScript 加密逻辑
# - 追踪数据流
# - 识别算法类型
# - 推导签名规则
```

#### Qwen3-Coder (编程模型)

```python
# 优势:
# - 代码生成能力强
# - 调试和修复能力好
# - 免费 API
# - 多语言支持

# 适用场景:
# - 生成签名代码
# - 调试错误
# - 代码优化
# - 自动化测试
```

---

## 3. 实现细节

### 3.1 API 配置

```python
# axelo/ai/dual_model_client.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    api_url: str
    api_key: str
    max_tokens: int
    temperature: float


class DualModelClient:
    """双模型客户端"""
    
    # DeepSeek R1 (免费)
    DEEPSEEK_CONFIG = ModelConfig(
        name="deepseek-reasoner",
        api_url="https://api.deepseek.com/v1/chat/completions",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        max_tokens=4096,
        temperature=0.7,
    )
    
    # Qwen3-Coder (免费 via OpenRouter)
    QWEN_CONFIG = ModelConfig(
        name="qwen/qwen3-coder:free",
        api_url="https://openrouter.ai/api/v1/chat/completions",
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        max_tokens=4096,
        temperature=0.5,
    )
    
    # Claude (备用)
    CLAUDE_CONFIG = ModelConfig(
        name="claude-3-5-sonnet-20241022",
        api_url="https://api.anthropic.com/v1/messages",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        max_tokens=4096,
        temperature=0.7,
    )
```

### 3.2 任务路由器

```python
class TaskRouter:
    """任务路由器 - 判断任务类型"""
    
    REASONING_KEYWORDS = [
        "分析", "推理", "理解", "追踪", "推导",
        "identify", "analyze", "trace", "derive",
    ]
    
    CODING_KEYWORDS = [
        "生成", "代码", "实现", "编写", "修复",
        "generate", "code", "implement", "write", "fix",
    ]
    
    def classify(self, task: Task) -> str:
        """分类任务"""
        
        combined = f"{task.goal} {task.description}".lower()
        
        has_reasoning = any(kw in combined for kw in self.REASONING_KEYWORDS)
        has_coding = any(kw in combined for kw in self.CODING_KEYWORDS)
        
        if has_reasoning and has_coding:
            return "hybrid"
        elif has_reasoning:
            return "reasoning_only"
        elif has_coding:
            return "coding_only"
        else:
            return "hybrid"  # Default to hybrid
```

### 3.3 结果验证

```python
class ResultValidator:
    """结果验证器"""
    
    def validate(self, result: ExecutionResult) -> bool:
        """验证执行结果"""
        
        # 检查是否有代码
        if not result.code:
            return False
        
        # 尝试运行代码
        if not self._can_execute(result.code):
            return False
        
        # 检查语法
        if not self._check_syntax(result.code):
            return False
        
        return True
    
    def _can_execute(self, code: str) -> bool:
        """检查代码是否可执行"""
        
        # 检查是否有 main 函数或可执行的代码块
        return "def " in code or "class " in code or "import " in code
    
    def _check_syntax(self, code: str) -> bool:
        """检查语法"""
        
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
```

---

## 4. 成本分析

### 4.1 成本估算

| 场景 | 免费模型 | Claude | 总成本 |
|------|----------|--------|--------|
| **成功 (80%)** | $0 | $0 | **$0** |
| **失败回退 (20%)** | $0 | $0.02-0.10 | **$0.02-0.10** |

### 4.2 预期成本

- 假设每天处理 100 个任务
- 80 个成功 → $0
- 20 个失败 → $0.02-0.10 × 20 = **$0.40-2.00 / 天**
- 每月成本 → **$12-60 / 月**

### 4.3 对比

| 方案 | 月成本 | 节省 |
|------|--------|------|
| 纯 Claude | $200-500 | - |
| **双模型协作** | $12-60 | **70-90%** |

---

## 5. 实施计划

### 5.1 第一阶段：基础架构 (Week 1)

| 任务 | 交付物 |
|------|--------|
| 创建 `dual_model_client.py` | 双模型客户端封装 |
| 配置 DeepSeek API | 推理模型集成 |
| 配置 Qwen API | 编程模型集成 |

### 5.2 第二阶段：编排逻辑 (Week 2)

| 任务 | 交付物 |
|------|--------|
| 实现任务路由器 | 任务分类 |
| 实现结果聚合器 | 结果合并 |
| 实现结果验证器 | 质量检查 |

### 5.3 第三阶段：回退机制 (Week 3)

| 任务 | 交付物 |
|------|--------|
| 配置 Claude 回退 | 失败时自动调用 |
| 实现重试逻辑 | 失败重试 |
| 记录失败日志 | 问题分析 |

### 5.4 第四阶段：测试优化 (Week 4)

| 任务 | 交付物 |
|------|--------|
| 单元测试 | 各模块测试 |
| 集成测试 | 端到端测试 |
| 性能优化 | 响应时间优化 |

---

## 6. API 密钥获取

### 6.1 DeepSeek (免费)

1. 访问 https://platform.deepseek.com/
2. 注册账号
3. 获取 API Key
4. 环境变量: `DEEPSEEK_API_KEY`

### 6.2 Qwen (免费 via OpenRouter)

1. 访问 https://openrouter.ai/
2. 注册账号
3. 获取 API Key
4. 环境变量: `OPENROUTER_API_KEY`

### 6.3 Claude (备用)

1. 访问 https://console.anthropic.com/
2. 获取 API Key
3. 环境变量: `ANTHROPIC_API_KEY`

---

## 7. 成功标准

### 7.1 功能标准

- [ ] DeepSeek R1 正确分析 JavaScript
- [ ] Qwen3-Coder 生成可运行代码
- [ ] 两个模型正确协作
- [ ] 失败时自动回退到 Claude
- [ ] 验证代码质量

### 7.2 性能标准

- [ ] 平均响应时间 < 30秒
- [ ] 免费模型成功率 > 80%
- [ ] Claude 回退响应时间 < 15秒

### 7.3 成本标准

- [ ] 月成本 < $100
- [ ] 免费模型使用率 > 80%

---

## 8. 文件结构

```
axelo/ai/
├── dual_model_client.py      # 双模型客户端
├── task_router.py             # 任务路由器
├── result_aggregator.py       # 结果聚合器
├── result_validator.py        # 结果验证器
├── fallback_handler.py        # 回退处理器
└── __init__.py               # 统一入口
```

---

**计划版本**: 1.0  
**创建日期**: 2026-04-07  
**预计完成**: 4 周  
**状态**: 等待审批