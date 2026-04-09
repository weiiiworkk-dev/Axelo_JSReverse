# Axelo 生产迁移计划：AI 对话式架构

## TL;DR

> **目标**: 将 Axelo JSReverse 从损坏的 CLI 状态迁移到完整的 AI 对话式生产就绪架构
> 
> **核心交付物**:
> - 可用的 CLI (`axelo run` + `axelo chat`)
> - 10 个生产级 MCP Tools
> - 真正的 AI 对话界面
> - 完整的会话状态管理

> **预估工时**: 8-12 天 (分 4 阶段)
> **并行执行**: 是 (各 Tool 独立实现)

---

## Context

### 当前状态

**已实现模块**:
- ✅ `axelo_chat.py` - 独立入口点 (可运行)
- ✅ `axelo/tools/base.py` - MCP Schema 定义
- ✅ `axelo/chat/router.py` - 对话路由器 (意图解析)
- ✅ `axelo/chat/executor.py` - 工具执行器
- ✅ `axelo/chat/ui.py` - 终端 UI

**存根模块** (需实现):
- `browser_tool.py` - 需集成 Playwright
- `fetch_tool.py` - 需实现真实 HTTP
- `static_tool.py` - 需接入现有分析逻辑
- `crypto_tool.py` - 需接入现有加密分析
- `ai_tool.py` - 需接入真实 AI API
- `codegen_tool.py` - 需基于分析结果生成

**已删除模块** (需恢复或替代):
- `axelo/orchestrator/master.py` - CLI 依赖
- `axelo/pipeline/stages/*` - 8 阶段流水线
- `axelo/wizard.py` - 向导界面

### 可复用现有模块

| 模块 | 位置 | 状态 | 复用方式 |
|------|------|------|----------|
| BrowserDriver | `axelo/browser/driver.py` | ✅ 完整 | 直接集成到 browser_tool |
| ActionRunner | `axelo/browser/action_runner.py` | ✅ 完整 | 执行动作序列 |
| SessionState | `axelo/models/session_state.py` | ✅ 完整 | 持久化 |
| StaticAnalyzer | `axelo/analysis/static/*.py` | ✅ 完整 | 接入 static_tool |
| CryptoDetector | `axelo/analysis/dynamic/crypto_detector.py` | ✅ 完整 | 接入 crypto_tool |
| VerificationEngine | `axelo/verification/engine.py` | ✅ 完整 | 接入 verify_tool |
| Storage | `axelo/storage/*.py` | ✅ 完整 | 持久化 |

### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     Axelo CLI (axelo run)               │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              ConversationRouter (对话式)               │
│   - 意图解析 (URL/Goal/Confirm)                        │
│   - 执行计划生成                                        │
│   - 人类确认点                                          │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                   MCP Tool Registry                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │ browser │ │  fetch  │ │ static  │ │  crypto │      │
│  │  tool   │ │  tool   │ │  tool   │ │  tool   │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │  ai_    │ │codegen  │ │ verify  │ │  flow   │      │
│  │ analyze │ │  tool   │ │  tool   │ │  tool   │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              执行引擎 (ToolExecutor)                    │
│   - 顺序执行/并行执行                                    │
│   - 状态传递                                            │
│   - 错误处理与重试                                      │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
      ┌──────────┐    ┌──────────┐    ┌──────────┐
      │ Playwright│    │  HTTP    │    │ 现有分析  │
      │  浏览器  │    │  请求    │    │  模块    │
      └──────────┘    └──────────┘    └──────────┘
```

---

## Work Objectives

### 核心目标

1. **修复 CLI**: 让 `axelo run` 和 `axelo chat` 都可用
2. **实现 Tool**: 10 个 MCP Tool 真实实现
3. **集成 AI**: 接入 LLM 实现智能对话
4. **生产就绪**: 会话持久化、错误恢复、日志追踪

### 交付定义

- [ ] `axelo run <url> --goal "xxx"` 可以执行完整流程
- [ ] `axelo chat` 启动对话界面，可交互
- [ ] 每个 Tool 有真实实现，不是存根
- [ ] AI 可以基于分析结果生成签名假设
- [ ] 代码生成基于真实分析，不是模板

---

## Execution Strategy

### Phase 1: 基础设施修复 (1-2天)

```
T1: 修复 CLI 导入问题
    ├── 1.1: 删除 orchestrator/platform 导入 (axelo/cli.py)
    ├── 1.2: 实现简化版 orchestrator 或替换为 tool 调用
    └── 1.3: 测试 `axelo run` 命令

T2: 统一入口点
    ├── 2.1: 合并 axelo_chat.py 到 axelo chat 子命令
    ├── 2.2: 添加 --help 支持
    └── 2.3: 测试 `axelo chat` 命令

T3: 工具注册初始化
    ├── 3.1: 创建 axelo/tools/__init__.py 自动注册
    ├── 3.2: 添加所有 10 个 Tool 的导入
    └── 3.3: 验证 ToolRegistry 工作正常
```

**依赖**: 无 (可直接开始)
**并行**: T1, T2, T3 独立

### Phase 2: Tool 实现 (3-5天)

```
T4: Browser Tool (Playwright 集成)
    ├── 4.1: 集成 BrowserDriver (axelo/browser/driver.py)
    ├── 4.2: 实现页面导航与动作执行
    ├── 4.3: 提取 cookies/localStorage/sessionStorage
    ├── 4.4: 捕获网络请求/响应
    └── 4.5: 提取 JS bundles

T5: Fetch Tool (HTTP 请求)
    ├── 5.1: 实现 HTTP 客户端 (httpx)
    ├── 5.2: 支持常见认证头
    ├── 5.3: 代理支持
    └── 5.4: 重试机制

T6: Static Tool (静态分析)
    ├── 6.1: 集成现有 static analysis (axelo/analysis/static/)
    ├── 6.2: 提取签名候选
    ├── 6.3: AST 分析
    └── 6.4: 模式匹配

T7: Crypto Tool (加密分析)
    ├── 7.1: 集成 CryptoDetector (axelo/analysis/dynamic/crypto_detector.py)
    ├── 7.2: 检测加密函数调用
    ├── 7.3: 提取密钥位置
    └── 7.4: 算法识别

T8: 其他 Tools 实现
    ├── 8.1: fetch_js_bundles - JS 下载
    ├── 8.2: honeypot_tool - 反检测
    ├── 8.3: flow_tool - 数据流分析
    └── 8.4: verify_tool - 集成验证引擎

T9: Verify Tool (验证)
    ├── 9.1: 集成 VerificationEngine (axelo/verification/engine.py)
    ├── 9.2: 实现请求对比
    ├── 9.3: 实现数据质量检查
    └── 9.4: 实现稳定性检查
```

**依赖**: T1, T3 完成
**并行**: T4-T9 可并行 (各自独立实现)

### Phase 3: AI 集成 (2-3天)

```
T10: AI 分析 Tool
    ├── 10.1: 接入 DeepSeek API (配置 API_KEY)
    ├── 10.2: 构建签名分析 prompt
    ├── 10.3: 实现假设生成
    ├── 10.4: 实现置信度评估
    └── 10.5: 解析 AI 返回的签名类型

T11: 代码生成 Tool
    ├── 11.1: 基于分析结果构建 prompt
    ├── 11.2: 生成 Python 代码
    ├── 11.3: 生成 JS bridge (可选)
    ├── 11.4: 生成 requirements.txt
    └── 11.5: 生成 manifest.json

T12: Router 增强 (LLM 意图理解)
    ├── 12.1: 接入 LLM 进行意图解析
    ├── 12.2: 动态生成执行计划
    ├── 12.3: 实现更智能的对话管理
    └── 12.4: 添加多轮对话支持
```

**依赖**: T4-T9 完成
**并行**: T10, T11, T12 独立

### Phase 4: 会话与生产就绪 (1-2天)

```
T13: 会话持久化
    ├── 13.1: 集成 SessionState (axelo/models/session_state.py)
    ├── 13.2: 保存/恢复 browser state
    ├── 13.3: 保存/恢复 cookies
    └── 13.4: 实现会话 ID 管理

T14: 错误处理与恢复
    ├── 14.1: 添加超时处理
    ├── 14.2: 实现重试机制
    ├── 14.3: 实现检查点保存
    └── 14.4: 实现从检查点恢复

T15: 日志与监控
    ├── 15.1: 集成 structlog
    ├── 15.2: 添加运行追踪 ID
    ├── 15.3: 实现结构化输出
    └── 15.4: 添加成本计算

T16: 清理与文档
    ├── 16.1: 删除废弃代码
    ├── 16.2: 添加 README 更新
    └── 16.3: 测试完整流程
```

**依赖**: T10-T12 完成
**并行**: T13-T16 独立
**最终验证**: 端到端测试

---

## Verification Strategy

### 测试策略

- **基础设施**: `python -c "from axelo.cli import app"` 无错误
- **Tool 注册**: `python -c "from axelo.tools.base import get_registry; print(len(get_registry().list_tools()))"` 输出 10
- **CLI 命令**: `axelo --help` 显示可用命令
- **Chat 对话**: 模拟输入 URL + Goal + Confirm，验证流程

### QA 场景

**场景 1: CLI 基本功能**
```bash
axelo --help
axelo info
```
预期: 显示帮助信息和系统配置

**场景 2: Chat 对话流程**
```python
# 模拟输入
input_data = [
    "amazon.com",
    "获取商品列表",
    "y"  # 确认执行
]
```
预期: 
- 识别 URL
- 识别 Goal
- 生成执行计划
- 确认后执行 Tool 序列

**场景 3: Tool 执行**
```python
from axelo.tools.base import get_registry
browser = get_registry().get("browser")
result = await browser.execute({"url": "https://example.com", "goal": "test"}, ToolState())
```
预期: 返回真实的执行结果 (非模拟)

---

## Commit Strategy

### Phase 1 提交
```
fix: 修复 CLI 导入问题，添加 chat 命令
- axelo/cli.py: 删除损坏的导入，添加 chat 子命令
- axelo/chat/cli.py: 完善 CLI 初始化
- axelo/tools/__init__.py: 添加 Tool 注册
```

### Phase 2 提交
```
feat: 实现核心 MCP Tools
- axelo/tools/browser_tool.py: 集成 BrowserDriver
- axelo/tools/fetch_tool.py: 实现 HTTP 客户端
- axelo/tools/static_tool.py: 集成静态分析
- axelo/tools/crypto_tool.py: 集成加密分析
- axelo/tools/verify_tool.py: 集成验证引擎
```

### Phase 3 提交
```
feat: 集成 AI 分析与代码生成
- axelo/tools/ai_tool.py: 接入 DeepSeek API
- axelo/tools/codegen_tool.py: 基于分析结果生成代码
- axelo/chat/router.py: 增强 LLM 意图理解
```

### Phase 4 提交
```
feat: 添加会话持久化与生产就绪特性
- axelo/chat/executor.py: 添加状态持久化
- 添加错误恢复机制
- 添加结构化日志
```

---

## Success Criteria

### 定义完成

| 阶段 | 验收条件 |
|------|----------|
| Phase 1 | `axelo --help` 无错误，`axelo chat` 可启动 |
| Phase 2 | 10 个 Tool 都可以执行并返回真实结果 |
| Phase 3 | AI 可以基于分析生成签名假设，代码可运行 |
| Phase 4 | 完整流程可端到端运行，会话可恢复 |

### 验证命令

```bash
# Phase 1
python -c "from axelo.cli import app; print('OK')"
axelo --help
axelo info

# Phase 2
python -c "
import asyncio
from axelo.tools.base import get_registry, ToolState
async def test():
    tools = get_registry()
    b = tools.get('browser')
    r = await b.execute({'url': 'https://example.com', 'goal': 'test'}, ToolState())
    print('Browser:', r.status.value)
asyncio.run(test())
"

# Phase 3
# 对话流程测试 - 输入 amazon.com -> 获取商品列表 -> y

# Phase 4
# 完整端到端测试
```

---

## Timeline

| 日期 | 任务 | 交付物 |
|------|------|--------|
| Day 1 | T1-T3: 基础设施修复 | CLI 可用 |
| Day 2-3 | T4-T5: Browser + Fetch | 基础 Tool |
| Day 4 | T6-T7: Static + Crypto | 分析 Tool |
| Day 5 | T8-T9: 其他 Tools | 完整 Tool 集 |
| Day 6-7 | T10-T11: AI 集成 | 智能分析 |
| Day 8 | T12: Router 增强 | 智能对话 |
| Day 9-10 | T13-T15: 生产就绪 | 可生产 |
| Day 11 | T16: 测试与清理 | 交付 |

---

## Risks & Mitigations

| 风险 | 影响 | 缓解 |
|------|------|------|
| 现有模块接口不兼容 | Tool 实现延迟 | 提前验证接口兼容性 |
| AI API 不稳定 | 对话功能受影响 | 添加降级到规则引擎 |
| Playwright 环境问题 | 浏览器功能失败 | 添加 headful 回退 |
| 内存泄漏 | 长会话崩溃 | 添加资源清理 |

---

## Open Questions

1. **Orchestrator 替代方案**: 是否需要恢复完整 orchestrator，还是用简化的 tool 调用替代？
2. **AI Provider 选择**: 使用 DeepSeek 还是 Anthropic？或者两者都支持？
3. **存储后端**: 使用现有文件存储还是需要数据库？
4. **测试策略**: 单元测试 vs 集成测试比例？

这些问题需要在开始前确认，以便准确评估工作量。