# 代码生成器修复与优化计划

## 问题概述

### 当前状态
- 验证系统已经修复（P1-P5全部完成）
- 但系统无法到达验证阶段，因为在代码生成阶段就失败了
- 错误：`name 'log' is not defined`

### 根本原因
代码生成器 (`codegen_services.py`) 生成的爬虫脚本中引用了`log`变量，但该变量未在生成的脚本中定义。

---

## 问题分析

### 1. 涉及的文件

| 文件 | 作用 | 问题 |
|------|------|------|
| `axelo/agents/codegen_services.py` | 代码生成主服务，定义了模块级`log` | `log = structlog.get_logger()`被生成脚本意外引用 |
| `axelo/ai/prompts/base_crawler_template.py` | 生成爬虫代码的模板 | 生成的脚本缺少logger初始化 |
| `axelo/agents/codegen_agent.py` | 代码生成代理 | 可能需要检查模板调用 |
| `axelo/pipeline/stages/s7_codegen.py` | 代码生成阶段 | 可能需要注入logger |

### 2. 代码流程

```
用户请求 → API扫描 → 目标选择 → 代码生成(s7_codegen) 
    ↓
codegen_services.py + 模板 → 生成爬虫脚本
    ↓
脚本保存到 workspace/sessions/*/output/*.py
    ↓
运行爬虫脚本 → 错误: "name 'log' is not defined" ❌
```

### 3. 问题触发点

- **阶段**: master阶段（s1-s4之后）
- **症状**: workflow_trace显示 `"stage_name": "master", "status": "failed"`
- **错误消息**: `"summary": "name 'log' is not defined"`

---

## 修复计划

### Phase G1: 修复Logger初始化 (最高优先级)

#### G1.1: 在base_crawler_template中添加logger初始化

文件: `axelo/ai/prompts/base_crawler_template.py`

在生成的爬虫脚本顶部添加:
```python
# 修复: 添加logger初始化
import logging
import sys

# 配置基础日志输出到stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# 兼容旧代码中的log引用
log = logger
```

#### G1.2: 验证模板是否包含log引用

检查所有模板文件，确保没有意外引用外部`log`:
- `axelo/ai/prompts/*.py`
- `axelo/ai/prompts/**/*.j2`

#### G1.3: 清理codegen_services中的log引用

文件: `axelo/agents/codegen_services.py`

在模板渲染时，移除可能传递的`log`变量:
```python
# 当前 (可能导致问题):
template.render(log=log, ...)

# 修改为 (移除log传递):
template.render(...)
```

---

### Phase G2: 增强代码生成健壮性

#### G2.1: 添加代码生成错误处理

在代码生成阶段添加异常捕获:
- 如果生成失败，记录详细错误
- 不要让生成错误直接传播到master

#### G2.2: 添加代码验证

生成爬虫脚本后，验证脚本可以import:
```python
def validate_generated_code(code: str) -> bool:
    try:
        compile(code, '<string>', 'exec')
        return True
    except SyntaxError as e:
        log.error("generated_code_syntax_error", error=str(e))
        return False
```

---

### Phase G3: 验证与测试

#### G3.1: 生成测试

修复后，对每个平台生成爬虫脚本:
```bash
python -m axelo.ui.main amazon --auto
python -m axelo.ui.main ebay --auto
python -m axelo.ui.main lazada --auto
python -m axelo.ui.main shopee --auto
```

#### G3.2: 验证脚本运行

检查生成的脚本:
1. 是否可以正确import
2. 是否可以执行（不需要成功，只需要不报NameError）
3. 是否可以到达验证阶段

#### G3.3: 检查验证分数

确认验证逻辑修复已生效（之前的P1-P5修复）:
- Comparator: 不再因为IGNORED字段导致0分
- Data Quality: 智能record_path
- Anti-Bot: 降低惩罚
- Stability: 首次运行宽容
- 整体评分: 加权+保护

---

## 详细任务清单

| Phase | 任务 | 文件 | 描述 |
|-------|------|------|------|
| G1 | G1.1 | base_crawler_template.py | 在模板中添加logger初始化 |
| G1 | G1.2 | base_crawler_template.py | 清理模板中的log引用 |
| G1 | G1.3 | codegen_services.py | 移除传递给模板的log变量 |
| G2 | G2.1 | s7_codegen.py | 添加代码生成错误处理 |
| G2 | G2.2 | codegen_services.py | 添加代码验证 |
| G3 | G3.1 | - | 测试Amazon生成 |
| G3 | G3.2 | - | 测试eBay生成 |
| G3 | G3.3 | - | 验证所有平台 |

---

## 预期结果

| 平台 | 修复前 | 修复后预期 |
|------|--------|------------|
| Amazon | 代码生成失败 | 代码生成成功，进入验证阶段 |
| eBay | 代码生成失败 | 代码生成成功，进入验证阶段 |
| Lazada | (未测试) | 代码生成成功 |
| Shopee | (未测试) | 代码生成成功 |

**最终目标**: 4个平台都能成功运行代码生成，进入验证阶段，并利用之前修复的验证逻辑获得≥60%的验证分数。

---

## 风险与回退

| 风险 | 应对方案 |
|------|----------|
| Logger可能影响爬虫性能 | 使用minimal配置，只输出必要信息 |
| 模板修改可能影响其他功能 | 先在测试环境验证 |
| 验证分数仍然低 | 利用P1-P5的修复，应该能提升 |

---

是否开始执行此修复计划?