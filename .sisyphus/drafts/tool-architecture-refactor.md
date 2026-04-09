# Tool Architecture Refactor - Design Decisions

## Core Objective
将现有的 8阶段硬编码 pipeline 重构为 **AI Router + Tool Ecosystem** 架构

## Architecture Vision - V2 (Conversation AI)

```
┌───────────────────────────────────────────────────────────┐
│              Conversational AI UI                        │
│  ┌──────────────────────────────────────────────┐    │
│  │  对话式交互界面 (Web/Terminal)              │    │
│  │                                          │    │
│  │  [AI] 你好！需要我帮你逆向什么网站？        │    │
│  │  [User] amazon.com                       │    │
│  │                                          │    │
│  │  [AI] 正在分析...                       │    │
│  │  [AI] 我的推理过程:                      │    │
│  │  1. 检测到目标需要登录                  │    │
│  │  2. 需要绕过 Cloudflare                 │    │
│  │  3. 签名在 /api/sig 中               │    │
│  │                                          │    │
│  │  [User] 确认，继续                    │    │
│  └──────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────┐
│          AI Conversation Router                  │
│  ┌───────────────────────────────────────┐    │
│  │  • 对话管理器 (理解多���对话)            │    │
│  │  • 思考过程输出引擎 ( Reasoning Out) │    │
│  │  • 任务规划器 (Task Planner)         │    │
│  │  • 人类干预点 (Human-in-the-loop)    │    │
│  └───────────────────────────────────────┘    │
└───────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────┐
│           Tool Executor (MCP Tools)              │
│  • 动态选择需要调用的 tools                │
│  • 状态管理                              │
│  • 错误处理和重试                        │
└───────────────────────────────────────────────────┘
```

## Conversation AI Features

| 功能 | 描述 |
|------|------|
| **主动询问** | AI 主动询问需求，而不是用户填表单 |
| **思考可视化** | 流式显示 AI 的推理过程 |
| **实时执行** | 每步执行实时展示结果 |
| **人类确认** | 执行前等待用户确认 |
| **多轮对话** | 支持多轮交互澄清需求 |

## Confirmed UI Decisions

### 11. UI 部署
- **选择**: Terminal
- **实现**: 命令行界面

### 12. 思考可视化
- **选择**: 两者都要
- **实现**: 流式思考输出 + 分步执行展示

### 13. 人类干预点
- **选择**: 开始前
- **实现**: 执行计划生成后，等待用户确认

---

## Design Decisions

### 1. Tool Format
- **Standard**: MCP (Model Context Protocol)
- **Rationale**: Anthropic 标准，可组合可复用，生态丰富

### 2. Router Model
- **Model**: DeepSeek (现有)
- **Responsibility**: 
  - 理解用户需求
  - 选择合适的 tools
  - 决定执行参数
  - 处理错误和重试
  - 生成最终代码

### 3. Platform Architecture
- **Strategy**: 全部替换
- **Rationale**: 新架构更清晰，旧架构作为参考备份

### 4. Priority
- **Level**: P0 - 核心重构
- **Scope**: 完整重写所有模块为 tool

## Existing Modules to Convert

| 模块 | Tool 名称 | 说明 |
|------|----------|------|
| s1_crawl | browser_tool | Playwright 抓取 |
| s2_fetch | fetch_tool | JS bundle 下载 |
| s3_deobfuscate | deobs_tool | 混淆正规化 |
| s4_static | static_tool | 静态分析 |
| s5_dynamic | dynamic_tool | 动态分析 |
| s6_ai_analyze | ai_tool | AI 分析 |
| s7_codegen | codegen_tool | 代码生成 |
| s8_verify | verify_tool | 验证 |
| honeypot_detector | honeypot_tool | 蜜罐检测 |
| crypto_patterns | crypto_tool | Crypto 检测 |
| data_flow_tracker | flow_tool | 数据流追踪 |

## Confirmed Design Decisions

### 5. State Management
- **Approach**: 独立存储
- **Implementation**: 每个 tool 有独立存储，结果写入共享存储
- **Rationale**: 解耦 tools，便于独立测试和替换

### 6. Unified Output Schema
- **Format**: 统一 JSON Schema
- **Implementation**: 所有 tool 输出使用统一格式

### 7. Old Code Handling
- **Strategy**: 删除
- **Rationale**: 简化项目，避免维护负担

---

## Open Questions (Remaining)

1. **Tool Schema**: MCP tool 的具体 schema 设计？
2. **具体 Tools**: 还需要拆解哪些现有模块为 tool？

---

## Confirmed Technical Decisions

### 8. Tool Dependencies
- **Approach**: 动态推断
- **Implementation**: Router 根据结果动态决定调用顺序
- **Rationale**: 更灵活，减少硬编码

### 9. Retry Strategy
- **Approach**: Router 统一处理
- **Implementation**: Router 统一决定重试和降级
- **Rationale**: 一致性管理，简化 tool 实现

### 10. Cost Control
- **Approach**: 预算限制
- **Implementation**: 设置单次运行最大预算
- **Rationale**: 简单直接，容易控制

---

## Complete Design Summary

| 决策项 | 选择 |
|--------|------|
| Tool 标准 | MCP |
| Router 模型 | DeepSeek |
| 平台架构 | 全部替换 |
| 优先级 | P0 |
| 状态管理 | 独立存储 |
| 输出格式 | 统一 Schema |
| 旧代码 | 删除 |
| 依赖声明 | 动态推断 |
| 重试策略 | Router 统一 |
| 成本控制 | 预算限制 |

---

## Next Steps
1. 设计 MCP tool schema
2. 拆解现有模块为 tool 接口
3. 实现 DeepSeek router
4. 集成测试
5. 端到端验证