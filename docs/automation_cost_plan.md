# Axelo 自动化主干与成本优化方案

## 1. 当前问题复盘

最近两次 Lazada 回归给出的信号已经很明确：

- CLI 过去只问“抓哪类数据”，不问“抓哪一个对象”，导致系统会拿首页或泛页面去猜目标。
- 主流程已经能自动走到 `s7_codegen`，但验证阶段还会因为 header 契约不完整、反爬字段不一致而失败。
- 单次运行成本已经落到约 `$0.84 ~ $0.90`，但对一个“搜索页 + 已知站点家族”的任务来说仍然偏高。

结论是：

- 现在最该做的不是继续放大 AI，而是把自动化主干做厚。
- AI 应该从“默认驱动器”降级成“歧义求解器”和“失败修复器”。

## 2. 目标架构

目标架构应当是：

- 自动化主干负责 80% 以上的常见站点。
- AI 只在自动化链路无法收敛时介入。
- 任何一次 AI 介入前，都必须先拿到结构化证据，而不是整包 JS 文本。

### 2.1 主干分层

#### A. 输入规范层

职责：

- 强制采集 `url + goal + target_hint`
- 对 URL 做页面类型识别：首页、搜索页、商品页、类目页、登录页、hash SPA
- 对任务边界做实体化：商品、搜索词、SKU、店铺、类目

原则：

- 没有目标对象时，不允许直接把“商品价格”任务当成完整任务。
- 泛入口页 + 泛目标时，只允许 `interactive`，不允许默认 `auto`。

#### B. 自动发现层

职责：

- 浏览器采集网络请求
- 按 `known_endpoint + target_hint + 站点家族规则` 对请求重排
- 尽快收敛到 `top 3~5` 候选目标请求

原则：

- 不是“抓到很多请求”，而是“快速缩小到少数高价值请求”。

#### C. 签名家族识别层

职责：

- 在不依赖 AI 的前提下，先识别是否属于已知家族：
  - MTOP / H5 token
  - HMAC(timestamp, nonce, sorted params)
  - AES 包裹
  - RSA 包裹
  - WebUMID / Baxia / 风控头注入
- 输出统一的 `SignatureSpec`

原则：

- 先家族化，再 codegen。
- 只要家族已知，就优先用模板生成，而不是让 LLM“重新发明”。

#### D. 代码模板层

职责：

- 基于 `SignatureSpec` 选择模板
- 填充 host、path、headers、cookies、sign steps、verify contract
- 固定输出验证器需要的字段：
  - `self._last_headers`
  - `self._last_request_url`
  - `crawl()` 结果

原则：

- 常见家族必须“模板优先，AI 兜底”。

#### E. 验证修复层

职责：

- 先做契约验证，再做真实回放
- 对失败做结构化分类：
  - host 错
  - cookie 缺
  - header mismatch
  - 风控拦截
  - 输出格式错

原则：

- AI 不应该直接看全文日志，而应该拿到结构化 diff 再修。

## 3. AI 在新架构里的位置

AI 只保留四类职责：

1. 未知签名家族解释

- 当规则引擎无法识别签名模式时，让 AI 从少量结构化证据中归纳算法。

2. 模板缺口补全

- 已识别家族，但缺少某一小段 header 组装逻辑时，让 AI 只补那一段。

3. 失败后定点修复

- 验证器已经指出“缺哪个 header / 哪个 host / 哪个 cookie”，AI 只做局部修补。

4. 新站点知识沉淀

- 把一次成功逆向总结为新规则、新模板、新特征，而不是每次重新分析。

AI 不再负责：

- 默认阅读全文 JS
- 默认从零生成整份 crawler
- 默认自己猜 host、cookie domain、目标对象

## 4. 把成本压到 1/10 的方案

目标：

- 当前典型任务：`$0.84 ~ $0.90`
- 目标成本：`$0.08 ~ $0.10`

### 4.1 成本拆解

当前高成本来源主要是三段：

- `s6_ai_analyze`：一次较重的分析调用
- `s7_codegen`：一次较重的代码生成调用
- 验证失败后的重复 AI / 重跑

### 4.2 压缩路径

#### 第一阶段：先砍 50% 以上

1. 家族识别前置

- 对 MTOP / HMAC / AES / RSA 这类高频模式，先用规则引擎输出 `SignatureSpec`
- 命中已知家族时跳过 `s6_ai_analyze`

预期：

- 常见站点直接少一次大模型调用

2. 模板 codegen 替代 AI codegen

- 对已知家族使用 Jinja / Python 模板生成 crawler
- 只有模板缺口时才触发 AI

预期：

- 再少一次大模型调用

3. 上下文截断

- 传给 AI 的永远是结构化候选：
  - top token candidates
  - top suspicious strings
  - normalized call graph summary
  - observed request context
- 不再直接传整包 JS 或大段 bundle 文本

预期：

- 单次 token 消耗下降 60% 以上

#### 第二阶段：把成本打到 1/10

4. 记忆命中即短路

- 以 `domain + signature family + endpoint fingerprint + target_hint digest` 建 adapter key
- 命中已验证模板时直接复用，不进 AI

预期：

- 重复站点成本接近 0

5. 两级模型路由

- 小模型：家族分类、失败总结、局部 patch
- 大模型：只处理未知家族和多次修复失败

预期：

- 即使触发 AI，也把均价压到原来的 10%~20%

6. 失败修复只做增量 AI

- 不再重新跑整套 analyze + codegen
- 只把 `verification diff + affected code block + structured spec` 发给 AI

预期：

- 单次失败修复成本下降 70% 以上

### 4.3 目标成本示意

#### 现在

- AI analyze: `$0.35 ~ $0.45`
- AI codegen: `$0.35 ~ $0.40`
- 其他冗余 / 重试: `$0.10+`
- 合计: `$0.84 ~ $0.90`

#### 目标

- 规则命中 + 模板生成: `$0`
- 小模型失败总结 / 局部 patch: `$0.02 ~ $0.05`
- 未知站点 fallback 大模型摊薄后均价: `$0.03 ~ $0.05`
- 合计均价: `$0.08 ~ $0.10`

## 5. 逆向能力优化路线

### P0：先把“能稳定收敛”做好

- 强制 `target_hint`
- 请求优先级重排
- 失败摘要结构化
- codegen 输出验证契约统一

### P1：把“已知家族”彻底自动化

- 增加 `SignatureFamilyDetector`
- 增加 `SignatureSpec` 模板库
- 增加 `HostGroundingResolver`
- 增加 `HeaderContractEmitter`

### P2：把“未知家族”变成可学习资产

- AI 输出不能只生成代码，必须同时生成：
  - 家族猜测
  - 证据列表
  - 可复用规则
  - 模板候选
- 成功后自动写入 adapter registry 和 pattern memory

### P3：形成闭环

- 每次验证失败都分类进入失败库
- 每类失败都映射到规则修复或模板修复
- AI 只处理规则库还没覆盖的余量

## 6. 建议的下一批落地任务

优先级从高到低：

1. 新增 `target_hint` 的 CLI/编排约束已经落地，下一步要让 planner 在缺 hint 时自动降级到 `interactive`
2. 新增 `SignatureFamilyDetector`，先覆盖 Lazada/MTOP、淘宝/MTOP、常见 HMAC 站
3. 新增模板化 codegen，已知家族不再走 AI codegen
4. 新增 `verification diff -> patch` 的局部修复链路
5. 新增 adapter 命中短路策略，把重复站点运行成本打到接近 0

## 7. 一句话原则

Axelo 后面的方向不该是“更会猜”，而应该是“更少猜”：

- 输入更明确
- 自动化主干更厚
- AI 只在自动化链路收不拢时补位
- 每次 AI 介入都必须沉淀成下一次可复用的规则或模板
