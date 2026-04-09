# AI Conversation Architecture - 详细工作计划

## TL;DR

> 将 Axelo 从 8 阶段硬编码 pipeline 重构为 **AI 对话式交互架构**，核心变化：
> - 终端 Wizard → AI 对话界面（AI 主动询问需求）
> - 硬编码阶段 → MCP Tools（动态选择执行）
> - 单一编排器 → AI Router（智能决策）
> 
> **交付物**: 新的 CLI 工具，支持对话式逆向工程
> **预估工作量**: Large（需要完整重构）
> **并行执行**: YES（5 个 waves）

---

## Context

### 原始需求
用户希望将现有的终端交互方式改为 AI 对话形式：
- AI 会主动询问需求
- 显示 AI 思考过程让人类可视化
- 自定义任务而不是填表单
- 人类在关键点确认干预

### 讨论决定的设计
见 `.sisyphus/drafts/tool-architecture-refactor.md`

---

## Work Objectives

### 核心目标
创建新一代 AI 驱动的逆向工程 CLI，支持：
1. 对话式交互（AI 主动询问 + 人类回答）
2. 思考过程可视化（流式输出）
3. 动态 Tool 执行（而非硬编码阶段）
4. 人类确认点（执行前暂停等待确认）

### 具体交付物
- [ ] 新 CLI: `axelo chat` 命令
- [ ] AI Conversation Router（对话理解 + 思考输出）
- [ ] MCP Tools（11+ 个重写的 tools）
- [ ] Terminal UI（带颜色、进度、思考流）
- [ ] 旧代码清理（删除老 pipeline）

### 定义为完成
- [ ] `axelo chat` 可以启动对话
- [ ] AI 可以理解用户需求（URL + Goal）
- [ ] AI 显示思考过程
- [ ] AI 生成执行计划并等待确认
- [ ] 执行后输出可运行的爬虫代码
- [ ] 旧 `axelo` 命令仍然可用（向后兼容）

### 必须有
- 对话式交互界面
- 流式思考输出
- 人类确认点
- 错误处理和重试

### 禁止有（Guardrails）
- 回到填表单式交互
- AI 决策过程对人类不可见
- 没有干预点的全自动执行

---

## Verification Strategy

### 测试决策
- ** Infrastructure exists**: YES
- **Automated tests**: YES (Tests After)
- **Framework**: pytest
- **Agent-Executed QA**: ALWAYS（每个 task 必须有 QA scenarios）

### QA Policy
每个 task 必须包含 agent-executed QA scenarios：
- 命令行测试（CLI 输入/输出）
- 对话流程测试（模拟用户输入）
- Tool 执行测试（验证 tool 输出）

---

## Execution Strategy

### 并行执行 Waves

```
WAVE 1 (Foundation - 所有人可以并行):
├── T1: 设计 MCP Tool Schema 标准
├── T2: 创建 Tool 基类和接口
├── T3: 设计对话消息格式
├── T4: 创建 Terminal UI 基础库
└── T5: 设置项目结构

WAVE 2 (Core - 可以并行):
├── T6: browser_tool (从 s1_crawl)
├── T7: fetch_tool (从 s2_fetch)
├── T8: static_tool (从 s4_static)
├── T9: crypto_tool (从 analysis.crypto)
└── T10: dynamic_tool (从 s5_dynamic)

WAVE 3 (AI + Tools - 可以并行):
├── T11: ai_tool (从 s6_ai_analyze)
├── T12: codegen_tool (从 s7_codegen)
├── T13: verify_tool (从 s8_verify)
├── T14: honeypot_tool (从 detection)
└── T15: flow_tool (从 data_flow_tracker)

WAVE 4 (Router - 依赖 T1-T5):
├── T16: AI Conversation Router (对话理解)
├── T17: 思考输出引擎 (Reasoning Output)
├── T18: 任务规划器 (Task Planner)
├── T19: 人类干预点 (Human-in-the-loop)
└── T20: 会话状态管理

WAVE 5 (Integration - 依赖所有前面):
├── T21: 主 CLI 入口 (axelo chat)
├── T22: 流式输出集成
├── T23: 错误处理统一
├���─ T24: 向后兼容 (老命令)
└── T25: 文档

FINAL (验证):
├── T26: 端到端对话测试
├── T27: 清理旧代码
└── T28: 发布
```

### 依赖矩阵

| Task | 依赖 | 阻塞 |
|------|------|------|
| T1-T5 | - | T6-T15, T16-T20 |
| T6-T15 | T1, T2 | T21-T25 |
| T16-T20 | T1-T5 | T21-T25 |
| T21-T25 | T6-T15, T16-T20 | T26-T28 |
| T26-T28 | T21-T25 | - |

### Agent Dispatch Summary

- **1**: **5** - T1 → `quick`, T2 → `quick`, T3 → `quick`, T4 → `visual-engineering`, T5 → `quick`
- **2**: **5** - T6 → `visual-engineering`, T7 → `quick`, T8 → `deep`, T9 → `deep`, T10 → `deep`
- **3**: **5** - T11 → `deep`, T12 → `deep`, T13 → `deep`, T14 → `deep`, T15 → `deep`
- **4**: **5** - T16 → `artistry`, T17 → `artistry`, T18 → `deep`, T19 → `quick`, T20 → `quick`
- **5**: **5** - T21 → `deep`, T22 → `visual-engineering`, T23 → `quick`, T24 → `quick`, T25 → `writing`
- **FINAL**: **3** - T26 → `unspecified-high`, T27 → `deep`, T28 → `unspecified-high`

---

## TODOs

- [ ] 1. 设计 MCP Tool Schema 标准

  **What to do**:
  - 研究 MCP (Model Context Protocol) 规范
  - 设计 tool 定义 JSON schema
  - 定义输入/输出格式
  - 确定 tool 调用方式

  **Must NOT do**:
  - 不使用非标准格式
  - 不硬编码特定模型

  **References**:
  - MCP 官方文档
  - 当前 pipeline 阶段定义

- [ ] 2. 创建 Tool 基类和接口

  **What to do**:
  - 创建 `axelo/tools/base.py`
  - 定义 `BaseTool` 抽象类
  - 实现 tool 注册机制
  - 实现 tool 调用逻辑

  **References**:
  - 当前 `axelo/pipeline/base.py` 作为参考

- [ ] 3. 设计对话消息格式

  **What to do**:
  - 定义 AI 消息格式
  - 定义用户消息格式
  - 定义系统消息格式
  - 设计思考输出格式

- [ ] 4. 创建 Terminal UI 基础库

  **What to do**:
  - 选择 Terminal UI 库 (rich/textual)
  - 创建颜色主题
  - 创建进度条组件
  - 创建对话气泡组件

  **Recommended Agent Profile**:
  > Select category + skills based on task domain
  - **Category**: `visual-engineering`
    - Reason: Terminal UI 需要视觉设计
  - **Skills**: []
    - `ultrabrain`: Not needed - straightforward implementation
  - **Skills Evaluated but Omitted**:
    - N/A

- [ ] 5. 设置项目结构

  **What to do**:
  - 创建 `axelo/chat/` 目录
  - 创建子模块结构
  - 设置 `__init__.py`
  - 配置导入路径

- [ ] 6. browser_tool (从 s1_crawl 重写)

  **What to do**:
  - 重写 s1_crawl 为 browser_tool
  - MCP 格式封装
  - 输入: url, goal, options
  - 输出: session, captures, cookies

- [ ] 7. fetch_tool (从 s2_fetch 重写)

  **What to do**:
  - 重写 s2_fetch 为 fetch_tool
  - MCP 格式封装
  - 输入: session, target
  - 输出: js_bundles

- [ ] 8. static_tool (从 s4_static 重写)

  **What to do**:
  - 重写 s4_static 为 static_tool
  - 包含 AST 分析
  - 包含 crypto 检测
  - 输入: js_bundles
  - 输出: candidates

- [ ] 9. crypto_tool (从 analysis.crypto 重写)

  **What to do**:
  - 重写 crypto 检测为 crypto_tool
  - AES/RSA/HMAC 检测
  - 输入: js_code
  - 输出: crypto_patterns

- [ ] 10. dynamic_tool (从 s5_dynamic 重写)

  **What to do**:
  - 重写 s5_dynamic 为 dynamic_tool
  - 运行时验证
  - 输入: code, test_inputs
  - 输出: runtime_behavior

- [ ] 11. ai_tool (从 s6_ai_analyze 重写)

  **What to do**:
  - 重写 s6_ai_analyze 为 ai_tool
  - DeepSeek 调用封装
  - Hypothesis 生成
  - 输入: candidates, context
  - 输出: signature_hypothesis

- [ ] 12. codegen_tool (从 s7_codegen 重写)

  **What to do**:
  - 重写 s7_codegen 为 codegen_tool
  - Python 代码生成
  - JS Bridge 生成
  - 输入: signature_hypothesis
  - 输出: crawler_code

- [ ] 13. verify_tool (从 s8_verify 重写)

  **What to do**:
  - 重写 s8_verify 为 verify_tool
  - 执行验证
  - 输入: crawler_code, target
  - 输出: verification_report

- [ ] 14. honeypot_tool (从 detection 重写)

  **What to do**:
  - 重写 honeypot_detector 为 honeypot_tool
  - MCP 格式封装
  - 输入: html, page
  - 输出: honeypot_report

- [ ] 15. flow_tool (从 data_flow_tracker 重写)

  **What to do**:
  - 重写 data_flow_tracker 为 flow_tool
  - 数据流分析
  - 输入: code
  - 输出: data_flow_graph

- [ ] 16. AI Conversation Router

  **What to do**:
  - 实现对话理解
  - 提取用户需求 (URL, Goal)
  - 理解多轮对话
  - 管理对话历史

  **Recommended Agent Profile**:
  > AI Router 核心，需要智能理解
  - **Category**: `artistry`
    - Reason: 对话理解需要创造性思维
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - N/A

- [ ] 17. 思考输出引擎

  **What to do**:
  - 流式输出思考过程
  - Markdown 格式化
  - 进度显示
  - AI 推理过程可视化

  **Recommended Agent Profile**:
  - **Category**: `artistry`
    - Reason: 需要漂亮的输出格式

- [ ] 18. 任务规划器

  **What to do**:
  - 分析需求
  - 生成 tool 执行计划
  - 决定执行顺序
  - 评估依赖

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 任务规划是复杂推理

- [ ] 19. 人类干预点

  **What to do**:
  - 执行前暂停
  - 显示执行计划
  - 等待用户确认 (y/n)
  - 处理确认/拒绝

- [ ] 20. 会话状态管理

  **What to do**:
  - 保存对话历史
  - 保存 Tool 执行状态
  - 支持恢复
  - 清理状态

- [ ] 21. 主 CLI 入口

  **What to do**:
  - 实现 `axelo chat` 命令
  - 启动对话界面
  - 循环等待输入
  - 处理退出

- [ ] 22. 流式输出集成

  **What to do**:
  - 流式处理 AI 响应
  - 实时显示思考
  - 实时显示执行进度

- [ ] 23. 错误处理统一

  **What to do**:
  - 统一错误格式
  - 友好错误提示
  - 重试逻辑

- [ ] 24. 向后兼容

  **What to do**:
  - 保留 `axelo run`
  - 保留 `axelo wizard`
  - 标记为 legacy

- [ ] 25. 文档

  **What to do**:
  - CLI 帮助文档
  - 示例对话
  - 迁移指南

- [ ] 26. 端到端对话测试

  **What to do**:
  - 模拟完整对话
  - 测试所有 tool 调用
  - 验证输出
  - 测试错误处理

- [ ] 27. 清理旧代码

  **What to do**:
  - 删除老 pipeline 阶段
  - 清理旧 wizard
  - 确认向后兼容

- [ ] 28. 发布

  **What to do**:
  - 版本号更新
  - 发布说明
  - 打包

---

## Final Verification Wave

- [ ] F1. Plan Compliance Audit - `oracle`
- [ ] F2. Code Quality Review - `unspecified-high`
- [ ] F3. Real Manual QA - `unspecified-high`
- [ ] F4. Scope Fidelity Check - `deep`

---

## Commit Strategy

- WAVE1: `feat(chat): foundation for AI conversation`
- WAVE2: `feat(chat): implement browser and fetch tools`
- WAVE3: `feat(chat): implement analysis tools`
- WAVE4: `feat(chat): implement AI router`
- WAVE5: `feat(chat): integrate CLI and ship`

---

## Success Criteria

### 验证命令
```bash
axelo chat --start  # 启动对话
# AI: 你好！需要我帮你逆向什么网站？
# > amazon.com
# [AI 思考过程...]
# [执行计划显示]
# 确认执行? y
# [Tool 执行...]
# [生成代码]
```

### 最终检查
- [ ] 所有对话功能正常
- [ ] 思考过程可见
- [ ] 人类可以干预
- [ ] 代码正确生成
- [ ] 旧命令仍可用