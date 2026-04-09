# Axelo 架构清理与迁移计划

## TL;DR

> **目标**: 清理断裂的 orchestrator 引用，完成新旧架构的彻底分离
> 
> **核心交付物**:
> - 修复/删除 4 个断裂引用文件
> - 确认 CLI 完整功能
> - 删除废弃的 modes 模块
> - 更新 README 文档
> 
> **预估工时**: 2-4 小时
> **并行执行**: 是

---

## Context

### 当前状态分析

**新架构 (已就绪)**:
| 模块 | 位置 | 状态 |
|------|------|------|
| MCP Tools | `axelo/tools/` | ✅ 10 tools registered |
| Chat CLI | `axelo/chat/cli.py` | ✅ Import 测试通过 |
| Router | `axelo/chat/router.py` | ✅ 意图解析 |
| Executor | `axelo/chat/executor.py` | ✅ 工具执行 |
| CLI Commands | `axelo/cli.py` | ✅ chat/tools/run |

**旧架构 (已删除)**:
| 模块 | 原位置 | 状态 |
|------|--------|------|
| Orchestrator | `axelo/orchestrator/` | ✅ 已删除 |
| Pipeline Stages | `axelo/pipeline/` | ✅ 已删除 |
| Wizard | `axelo/wizard.py` | ✅ 已删除 |

**断裂引用 (需清理)**:
| 文件 | 问题 | 影响 |
|------|------|------|
| `axelo/session.py` | 直接 import MasterOrchestrator | ❌ Import 失败 |
| `axelo/platform_/workers.py` | import MasterOrchestrator | ❌ Platform 功能损坏 |
| `axelo/ui/executor.py` | import MasterOrchestrator | ❌ UI 功能损坏 |
| `axelo/core/engine.py` | Lazy import orchestrator | ⚠️ 潜在错误 |

---

## Work Objectives

### 核心目标

1. **修复断裂引用** - 4 个文件需要处理
2. **验证 CLI 功能** - 确保 axelo run/chat 正常工作
3. **清理废弃代码** - 删除不必要的依赖
4. **更新文档** - 反映新架构

### 具体要求

- **必须保持**: 新架构 (tools/ + chat/) 完整可用
- **必须删除**: 所有 orchestrator 依赖代码
- **必须验证**: `axelo run` 和 `axelo chat` 能正常执行

---

## Verification Strategy

### 测试命令
```bash
# 1. CLI 基础测试
python -c "from axelo.cli import app; print('CLI OK')"

# 2. Chat 模块测试
python -c "from axelo.chat.cli import AxeloChatCLI; print('Chat OK')"

# 3. Tools 注册测试
python -c "from axelo.tools.base import get_registry; print(len(get_registry().list_tools()))"

# 4. 完整命令测试
axelo --help
axelo info
axelo tools
```

### 验收标准
- [ ] `axelo run <url>` 不报 ImportError
- [ ] `axelo chat` 可以启动
- [ ] `axelo tools` 显示 10 tools
- [ ] 无 orchestrator 相关的 ImportError

---

## Execution Strategy

### 任务拆分

**Wave 1: 分析与决策** (可并行)
- [ ] 1. 分析 4 个断裂文件的具体用法
- [ ] 2. 决定每个文件的处理方式 (删除/重写/替换)
- [ ] 3. 确认 platform 模块的依赖关系

**Wave 2: 修复断裂引用** (顺序执行)
- [ ] 4. 修复/删除 axelo/session.py
- [ ] 5. 修复/删除 axelo/platform_/workers.py 的 orchestrator 引用
- [ ] 6. 修复 axelo/ui/executor.py 的 orchestrator 引用
- [ ] 7. 清理 axelo/core/engine.py 的 lazy import

**Wave 3: 验证与清理** (可并行)
- [ ] 8. 运行所有测试命令验证修复
- [ ] 9. 检查并清理废弃的 modes 模块 (可选)
- [ ] 10. 更新 README 反映新架构

---

## TODOs

- [ ] 1. 分析断裂引用文件

  **What to do**:
  - 读取 axelo/session.py 完整内容，理解其用途
  - 读取 axelo/platform_/workers.py 中 MasterOrchestrator 的使用方式
  - 读取 axelo/ui/executor.py 中的调用逻辑
  - 读取 axelo/core/engine.py 的 lazy import 逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 文件分析任务，简单快速
  - **Skills**: []
  - **Skills Evaluated but Omitted**:

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)
  - **Blocks**: [Task 4]
  - **Blocked By**: None

  **References**:
  - `axelo/cli.py:249-298` - CLI 成功处理 orchestrator 不存在的逻辑

  **Acceptance Criteria**:
  - [ ] 理解每个文件的用途
  - [ ] 确定修复策略

  **Commit**: NO

---

- [ ] 2. 决定每个文件的处理方式

  **What to do**:
  - session.py: 重写为调用新 chat CLI 或标记为废弃
  - platform_/workers.py: 移除 orchestrator 依赖，使用新架构
  - ui/executor.py: 重写为使用新工具架构
  - core/engine.py: 移除 lazy import 或提供替代

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)
  - **Blocks**: [Task 4]
  - **Blocked By**: None

  **Acceptance Criteria**:
  - [ ] 每个文件有明确的处理策略

  **Commit**: NO

---

- [ ] 3. 确认 platform 模块的依赖关系

  **What to do**:
  - 检查 platform_/workers.py 对 orchestrator 的依赖程度
  - 确定是否可以完全移除或需要替代
  - 验证 platform 功能是否独立于 orchestrator

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: [Task 5]
  - **Blocked By**: None

  **Acceptance Criteria**:
  - [ ] 了解 platform 模块的完整依赖

  **Commit**: NO

---

- [ ] 4. 修复/删除 axelo/session.py

  **What to do**:
  - 选项 A: 删除文件 (如果只是 facade)
  - 选项 B: 重写为调用 AxeloChatCLI
  - 选项 C: 标记为废弃并移除 orchestrator 引用

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: [Task 8]
  - **Blocked By**: [Task 1, 2]

  **Acceptance Criteria**:
  - [ ] 文件不再 import 不存在的模块

  **Commit**: YES
  - Message: fix(session): remove orchestrator dependency
  - Files: axelo/session.py

  **Commit**: NO

---

- [ ] 5. 修复 axelo/platform_/workers.py

  **What to do**:
  - 移除 MasterOrchestrator 导入
  - 重构 ReverseWorker 使用新的 chat 架构
  - 或提供降级实现

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: [Task 8]
  - **Blocked By**: [Task 3]

  **Acceptance Criteria**:
  - [ ] platform workers 不再依赖 orchestrator

  **Commit**: YES
  - Message: fix(platform): remove orchestrator dependency
  - Files: axelo/platform_/workers.py

  **Commit**: NO

---

- [ ] 6. 修复 axelo/ui/executor.py

  **What to do**:
  - 重写为使用新工具架构
  - 或移除 orchestrator 调用，改用 AxeloChatCLI

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: [Task 8]
  - **Blocked By**: [Task 2]

  **Acceptance Criteria**:
  - [ ] UI executor 正常工作

  **Commit**: YES
  - Message: fix(ui): integrate new tool architecture
  - Files: axelo/ui/executor.py

  **Commit**: NO

---

- [ ] 7. 清理 axelo/core/engine.py

  **What to do**:
  - 移除对不存在模块的 lazy import
  - 或提供新架构的替代

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: [Task 8]
  - **Blocked By**: [Task 1]

  **Acceptance Criteria**:
  - [ ] core/engine.py 不再有断裂引用

  **Commit**: YES
  - Message: fix(core): clean up deprecated imports
  - Files: axelo/core/engine.py

  **Commit**: NO

---

- [ ] 8. 运行测试验证修复

  **What to do**:
  - 运行所有验证命令
  - 检查是否有新的 ImportError
  - 验证 axelo run/chat 功能

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: [Task 9, 10]
  - **Blocked By**: [Task 4, 5, 6, 7]

  **Acceptance Criteria**:
  - [ ] python -c "from axelo.cli import app" 成功
  - [ ] axelo --help 正常
  - [ ] 无 ImportError

  **Commit**: NO

---

- [ ] 9. 检查废弃的 modes 模块

  **What to do**:
  - 检查 axelo/modes 的使用情况
  - 决定是否移除或保留
  - 检查是否有 deprecation warning

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 10)
  - **Blocks**: []
  - **Blocked By**: [Task 8]

  **Acceptance Criteria**:
  - [ ] modes 模块状态明确

  **Commit**: NO

---

- [ ] 10. 更新 README 反映新架构

  **What to do**:
  - 更新 README.md 中的架构描述
  - 添加新命令说明 (axelo chat, axelo tools)
  - 移除过时的 orchestrator 描述

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []
  - **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 9)
  - **Blocks**: []
  - **Blocked By**: [Task 8]

  **Acceptance Criteria**:
  - [ ] README 反映当前架构

  **Commit**: YES
  - Message: docs: update architecture for tool-based system
  - Files: README.md

  **Commit**: NO

---

## Final Verification Wave

- [ ] F1. 运行所有测试命令

  验证:
  - python -c "from axelo.cli import app"
  - python -c "from axelo.chat.cli import AxeloChatCLI"
  - python -c "from axelo.tools.base import get_registry; print(len(get_registry().list_tools()))"
  - axelo --help
  - axelo info
  - axelo tools

  Output: 每个命令的输出结果

- [ ] F2. 检查是否有新的断裂引用

  使用 grep 搜索:
  - from axelo.orchestrator
  - from axelo.pipeline
  - import MasterOrchestrator

  Output: 搜索结果

- [ ] F3. 验证 axelo run 和 axelo chat

  运行:
  - axelo run https://example.com --goal "测试" (或使用 --help 检查参数)
  - axelo chat --help

  Output: 命令输出

---

## Commit Strategy

- **1**: fix(session): remove orchestrator dependency | axelo/session.py
- **2**: fix(platform): remove orchestrator dependency | axelo/platform_/workers.py
- **3**: fix(ui): integrate new tool architecture | axelo/ui/executor.py
- **4**: fix(core): clean up deprecated imports | axelo/core/engine.py
- **5**: docs: update architecture for tool-based system | README.md

---

## Success Criteria

### 验证命令
```bash
# 必须全部通过
python -c "from axelo.cli import app"  # 无错误
python -c "from axelo.chat.cli import AxeloChatCLI"  # 无错误
python -c "from axelo.tools.base import get_registry; print(len(get_registry().list_tools()))"  # 输出 10
axelo --help  # 显示命令列表
axelo info  # 显示配置
axelo tools  # 显示 10 tools
```

### 最终检查清单
- [ ] 所有断裂引用已修复或删除
- [ ] CLI 功能完整可用
- [ ] 新架构 (tools + chat) 正常工作
- [ ] 无 ImportError
- [ ] README 已更新