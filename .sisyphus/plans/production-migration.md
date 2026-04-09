# Axelo AI Conversation Architecture - Production Migration Plan

## TL;DR

> 将 Axelo 从 8 阶段硬编码 pipeline 完全迁移到 **AI 对话式架构**
> - 新架构: AI Router + MCP Tools + Terminal UI
> - 目标: 生产就绪
> 
> **交付物**: 可运行的 `axelo chat` 命令
> **预估工作量**: XL (需要完整迁移 + 删除旧代码)
> **并行执行**: YES (多个 waves)

---

## Context

### 当前状态 (已实现)
- MCP Tool Schema: ✅
- 10 个 Tools: ✅ (已注册)
- ConversationRouter: ✅ (基础框架)
- CLI chat 命令: ✅ (已添加)
- Terminal UI: ✅

### 当前问题
1. Router 没有真正执行 Tools - 只是模拟
2. 没有 Tool 执行引擎
3. CLI 无法运行 (platform 模块冲突)
4. 旧 pipeline 仍在运行

### 迁移目标
- 新架构完全替代旧架构
- `axelo chat` 可生产运行
- 旧代码完全删除

---

## Work Objectives

### 核心目标
1. 实现 Tool 执行引擎 (Router → 真正调用 Tools)
2. 修复 CLI 运行 (解决 platform 冲突)
3. 实现完整对话流程 (理解 → 分析 → 执行 → 输出)
4. 删除旧架构 (pipeline, wizard, orchestrator)

### 具体交付物
- [ ] Router 可真正调用 Tools 并执行
- [ ] CLI `axelo chat` 可以启动对话
- [ ] 完整对话流程可工作
- [ ] 旧代码完全删除

### 定义为完成
- [ ] `axelo chat` 启动成功
- [ ] 输入 URL + Goal → 生成爬虫代码
- [ ] 旧 pipeline 无法运行 (已删除)
- [ ] `axelo run` 仍可用 (向后兼容)

### 必须有
- Tool 执行引擎
- 错误处理和重试
- 进度显示
- 结果输出

### 禁止有 (Guardrails)
- 旧 pipeline 代码残留
- 无法运行的 CLI
- 无错误处理

---

## Verification Strategy

### 测试决策
- **Infrastructure exists**: YES
- **Automated tests**: YES
- **Framework**: pytest
- **Agent-Executed QA**: ALWAYS

---

## Execution Strategy

### 并行执行 Waves

```
WAVE 1 (Tool Executor - 核心):
├── T1: 实现 ToolExecutor 类
├── T2: 实现路由器调用 Tools
├── T3: 实现状态管理 (ToolState 传递)
└── T4: 实现错误处理和重试

WAVE 2 (CLI Fix - 可并行):
├── T5: 修复 platform 模块冲突
├── T6: 修复 CLI 导入
├── T7: 测试 chat 命令
└── T8: 修复 Rich 依赖

WAVE 3 (Integration - 依赖 T1-T4):
├── T9: 集成 Router + Executor
├── T10: 实现进度显示
├── T11: 实现结果输出
└── T12: 端到端测试

WAVE 4 (Cleanup - 可并行):
├── T13: 删除 old pipeline stages
├── T14: 删除 old wizard
├── T15: 删除 old orchestrator
├── T16: 更新 imports
└── T17: 更新文档

FINAL (验证):
├── T18: 生产验证
├── T19: 向后兼容测试
└── T20: 发布准备
```

### 依赖矩阵

| Task | 依赖 | 阻塞 |
|------|------|------|
| T1-T4 | - | T5-T8, T9-T12 |
| T5-T8 | - | - |
| T9-T12 | T1-T4 | T13-T17 |
| T13-T17 | T9-T12 | T18-T20 |
| T18-T20 | T13-T17 | - |

---

## TODOs

- [ ] 1. 实现 ToolExecutor 类

  **What to do**:
  - 创建 `axelo/chat/executor.py`
  - 实现 `execute_tool(name, input_data)` 方法
  - 实现 `execute_sequence(tools, initial_input)` 方法
  - 实现状态传递 (ToolState)

  **References**:
  - `axelo/tools/base.py` - ToolRegistry
  - `axelo/chat/router.py` - ConversationRouter

- [ ] 2. 实现路由器调用 Tools

  **What to do**:
  - 修改 `ConversationRouter._create_execution_plan()`
  - 调用 ToolExecutor 执行真实 tools
  - 返回真实执行结果

  **References**:
  - `axelo/chat/router.py` - _create_execution_plan

- [ ] 3. 实现状态管理

  **What to do**:
  - ToolState 跨 tool 传递
  - 存储中间结果
  - 支持恢复

  **References**:
  - `axelo/tools/base.py` - ToolState

- [ ] 4. 实现错误处理和重试

  **What to do**:
  - 捕获 Tool 执行错误
  - 实现重试逻辑
  - 友好错误提示

- [ ] 5. 修复 platform 模块冲突

  **What to do**:
  - 重命名 `axelo/platform/` 为 `axelo/platform_/`
  - 更新所有 imports
  - 验证无冲突

- [ ] 6. 修复 CLI 导入

  **What to do**:
  - 修复 `axelo/cli.py` imports
  - 修复 chat CLI 导入

- [ ] 7. 测试 chat 命令

  **What to do**:
  - 运行 `axelo chat --help`
  - 运行 `axelo chat` 启动

- [ ] 8. 修复 Rich 依赖

  **What to do**:
  - 检查 Rich 库依赖
  - 确保 UI 正常工作

- [ ] 9. 集成 Router + Executor

  **What to do**:
  - Router 调用 Executor
  - 完整流程测试

- [ ] 10. 实现进度显示

  **What to do**:
  - 显示当前 tool
  - 显示执行进度
  - 显示预计时间

- [ ] 11. 实现结果输出

  **What to do**:
  - 显示生成的代码
  - 显示验证结果

- [ ] 12. 端到端测试

  **What to do**:
  - 模拟完整对话
  - 验证输出正确

- [ ] 13. 删除 old pipeline stages

  **What to do**:
  - 删除 `axelo/pipeline/stages/`
  - 删除 `axelo/pipeline/__init__.py` (如果只是 wrapper)
  - 删除 `axelo/pipeline/base.py` (如果不再使用)

- [ ] 14. 删除 old wizard

  **What to do**:
  - 删除 `axelo/wizard.py`
  - 删除 `axelo/ui/wizard/`

- [ ] 15. 删除 old orchestrator

  **What to do**:
  - 删除 `axelo/orchestrator/`
  - 删除 `axelo/core/engine/` (如果重复)

- [ ] 16. 更新 imports

  **What to do**:
  - 检查所有 imports
  - 更新到新架构

- [ ] 17. 更新文档

  **What to do**:
  - 更新 README
  - 更新 CLI 帮助

- [ ] 18. 生产验证

  **What to do**:
  - 真实目标测试
  - 边界情况测试

- [ ] 19. 向后兼容测试

  **What to do**:
  - 测试 `axelo run` (如果保留)
  - 测试其他命令

- [ ] 20. 发布准备

  **What to do**:
  - 版本号更新
  - 发布说明

---

## Final Verification Wave

- [ ] F1. Plan Compliance Audit - `oracle`
- [ ] F2. Code Quality Review - `unspecified-high`
- [ ] F3. Real Manual QA - `unspecified-high`
- [ ] F4. Scope Fidelity Check - `deep`

---

## Commit Strategy

- WAVE1: `feat(chat): implement tool executor`
- WAVE2: `fix(chat): resolve platform module conflict`
- WAVE3: `feat(chat): integrate router and executor`
- WAVE4: `refactor(chat): remove old pipeline code`
- FINAL: `release: chat command production ready`

---

## Success Criteria

### 验证命令
```bash
axelo chat --help
axelo chat
# 输入: amazon.com
# 输入: 获取商品列表
# 确认 y
# 等待执行...
# 输出: 生成的爬虫代码
```

### 最终检查
- [ ] chat 命令可运行
- [ ] 对话流程完整
- [ ] 代码正确生成
- [ ] 旧代码已删除
- [ ] 向后兼容命令仍可用