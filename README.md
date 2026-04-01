# Axelo JSReverse

Axelo JSReverse 是一个面向网页请求签名、Token 生成逻辑和 JS 混淆逆向的自动化系统。它会先抓取目标站点请求和 JS 资源，再做静态/动态分析，交给 AI 归纳算法假设，最后生成可运行的 Python 爬虫或 JS bridge 方案，并通过验证层回放确认结果。

## 当前架构

- `axelo/cli.py`：命令行入口。
- `axelo/wizard.py`：交互式向导入口，当前为 9 步。
- `axelo/orchestrator/master.py`：主编排器，负责抓取、分析、AI、生成、验证、记忆库写回。
- `axelo/pipeline/stages/`：分阶段流水线实现。
- `axelo/models/`：运行时数据模型与统一输入契约。
- `axelo/ai/`：Anthropic 调用与提示词模板。
- `axelo/browser/`：Playwright 浏览器、指纹和网络拦截。
- `axelo/analysis/`：JS 静态/动态分析工具。
- `axelo/memory/`：记忆库、检索和模板复用。
- `axelo/verification/`：生成代码回放验证。
- `axelo/output/`：输出保存逻辑。
- `axelo/policies/`：运行策略解析。
- `axelo/telemetry/`：结构化运行报告。

## 向导步骤

1. 目标 URL
2. 爬取目标数据类型
3. 目标接口特征
4. 反爬虫防护类型
5. 是否需要登录
6. 数据输出格式
7. 爬取频率偏好
8. 运行模式
9. AI 预算

## 运行方式

CLI：

```bash
axelo run https://example.com \
  --goal "分析并复现请求签名/Token生成逻辑" \
  --mode interactive \
  --budget 3 \
  --known-endpoint /api/search \
  --antibot cloudflare \
  --login cookie \
  --output-format json_file \
  --crawl-rate conservative
```

交互式向导：

```bash
AxeloJsReverse
```

## 新增输入字段

这些字段会进入 `RunConfig`，并透传到主编排器、AI prompt、运行策略和运行报告中：

- `known_endpoint`
- `antibot_type`
- `requires_login`
- `output_format`
- `crawl_rate`

## 输出物

每次运行会在会话目录下生成：

- `crawl/captures.json`
- `crawl/target.json`
- `output/crawler.py`
- `output/bridge_server.js`
- `output/requirements.txt`
- `run_report.json`

## 验证

建议先做这几个检查：

```bash
python -c "from axelo.models.target import TargetSite; print('ok')"
python -c "from axelo.orchestrator.master import MasterOrchestrator; print('ok')"
pytest -q tests/unit/test_run_config_policy.py tests/unit/test_verification.py
```

## 依赖

- Python 3.14+
- Node.js
- Playwright
- Anthropic API Key

## 说明

这套系统同时保留了旧的 `axelo/session.py` 路径，但当前推荐以 `MasterOrchestrator` 为主路径。

