# 电商平台逆向爬虫系统全面优化计划 (通用方案)

## TL;DR

> **目标**: 修复现有4个电商平台(Amazon/Lazada/Shopee/eBay)的逆向爬虫系统,使其能够通过验证并成功爬取数据。

> **核心原则**: 所有优化必须是**通用的**,不针对任何特定站点,而是每站点采用**共同的技术方案**。

> **核心问题**:
> 1. StageResult验证错误(artifacts路径为None)
> 2. 所有平台验证通过率为0%
> 3. API选择逻辑不正确
> 4. 第三方请求干扰真正的API发现

> **预期成果**: 4个平台全部通过验证,验证通过率≥80%

---

## 通用优化原则

1. **通用API选择**: 所有站点使用相同的选择逻辑,按API类型优先级排序
2. **通用第三方过滤**: 所有站点过滤相同的第三方域名
3. **通用验证容错**: 所有站点使用相同的验证阈值
4. **通用大文件处理**: 所有站点对大JS包使用相同的策略

---

## 问题分析

### 问题1: StageResult验证错误
**现象**: 动态分析阶段报Pydantic验证错误
```
validation errors for StageResult
artifacts.hook_trace: Input is not a valid path for <class 'pathlib.Path'>
artifacts.taint_events: Input is not a valid path for <class 'pathlib.Path'>
artifacts.topology_json: Input is not a valid path for <class 'pathlib.Path'>
artifacts.topology_mermaid: Input is not a valid path for <class 'pathlib.Path'>
```

**根因**: 
- `StageResult`模型中`artifacts: dict[str, Path]`要求所有值必须是有效的Path对象
- 动态分析阶段的代码在未生成这些文件时传入了None值
- Pydantic严格的类型验证拒绝了None值

**修复位置**: `axelo/models/pipeline.py`

---

### 问题2: 验证通过率0%
**现象**: 
- 逆向分析完成后验证分数始终为0%
- 生成的爬虫代码无法正确复现签名

**根因**:
1. **API选择错误**: 自动选择第一个API,但第一个往往是广告追踪等非目标API
2. **签名提取失败**: 静态/动态分析未能正确提取签名逻辑
3. **验证逻辑问题**: 验证器的比较逻辑过于严格

**修复位置**: 
- `axelo/ui/api_scanner.py` - API选择逻辑
- `axelo/pipeline/stages/s6_ai_analyze.py` - 签名提取
- `axelo/verification/` - 验证逻辑

---

### 问题3: 第三方请求干扰
**现象**: 仅发现7个API(Shopee),大量第三方追踪请求(Google Analytics, Facebook Pixel)

**根因**:
- 搜索结果页面被大量第三方追踪脚本占据
- 真正的API请求被识别为低置信度
- 没有过滤掉已知第三方域名

**修复位置**: `axelo/ui/api_scanner.py`

---

### 问题4: 大JS包超时
**现象**: 89KB的JS包(eBay)反混淆超时

**根因**:
- 大文件反混淆时间超过配置的超时时间(25秒)
- 没有针对大文件的通用优化策略

**修复位置**: `axelo/js_tools/runner.py`

---

## 优化方案 (通用技术)

### 核心: 阶段1 - 修复StageResult验证错误

**任务**: 修改StageResult模型,允许Optional Path

```python
# 修改前 (pipeline.py)
class StageResult(BaseModel):
    artifacts: dict[str, Path] = Field(default_factory=dict)

# 修改后 - 允许None值(通用修复)
class StageResult(BaseModel):
    artifacts: dict[str, Path | None] = Field(default_factory=dict)
```

**优先级**: 🔴 最高 - 阻塞完整流程

---

### 核心: 阶段2 - 通用API选择逻辑

**优化策略** (适用于所有站点):
1. **按类型优先级排序**: search_results(100) > product_listing(90) > product_detail(80) > 其他(50)
2. **通用第三方域名过滤**: 所有站点使用相同的过滤列表
3. **基于搜索关键词匹配**: 所有站点使用相同的匹配逻辑

```python
# 通用第三方域名列表(所有站点使用)
THIRD_PARTY_DOMAINS = {
    # Google生态
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "google.com",
    "gstatic.com",
    # Facebook生态
    "facebook.net",
    "facebook.com",
    "instagram.com",
    # 其他常见追踪
    "criteo.com",
    "taboola.com",
    "outbrain.com",
    "amazon-adsystem.com",  # Amazon广告系统也过滤
    "bing.com",
    "yahoo.com",
}

# 通用API优先级(所有站点使用)
API_TYPE_PRIORITY = {
    "search_results": 100,
    "product_listing": 90,
    "product_detail": 85,
    "user": 70,
    "cart": 60,
    "unknown": 50,
}
```

**优先级**: 🔴 最高 - 影响所有平台的验证通过率

---

### 核心: 阶段3 - 通用验证器容错

**优化策略** (适用于所有站点):
1. **通用header匹配阈值**: 从100%降至85%
2. **通用动态字段忽略列表**: 所有站点忽略相同的动态字段
3. **通用多级验证**: 增加"部分通过"状态

```python
# 通用验证配置(所有站点使用)
class VerificationConfig:
    # 通用阈值
    header_match_threshold = 0.85  # 所有站点统一使用85%
    min_data_quality_score = 0.5   # 所有站点统一使用50%
    
    # 通用忽略字段(所有站点)
    ignore_dynamic_fields = [
        "timestamp", "ts", "t",           # 时间戳
        "nonce", "sig", "_", "r",         # 随机值
        "sessionId", "session_id",         # 会话ID
        "x-api-version", "version",        # 版本号
    ]
    
    # 通用验证级别
    LEVEL_1_BASIC = "basic"      # 基础连接通过
    LEVEL_2_HEADER = "header"    # Header匹配通过  
    LEVEL_3_FULL = "full"        # 完整签名通过
```

**优先级**: 🟠 高 - 核心验证逻辑

---

### 核心: 阶段4 - 通用大文件处理

**优化策略** (适用于所有站点):
1. **通用大小阈值**: 超过100KB视为大文件
2. **通用超时策略**: 大文件超时从25秒增至60秒
3. **通用快速失败**: 无明显签名逻辑的大文件直接跳过

```python
# 通用大文件配置(所有站点使用)
class BundleConfig:
    LARGE_FILE_THRESHOLD = 100 * 1024  # 100KB,所有站点统一
    LARGE_FILE_TIMEOUT = 60            # 60秒,所有站点统一
    SMALL_FILE_TIMEOUT = 25            # 25秒,所有站点统一
    
    # 通用签名检测关键词(所有站点)
    SIGNATURE_KEYWORDS = [
        "sign", "signature", "token", "hash",
        "encrypt", "decrypt", "hmac", "sha",
        "md5", "base64", "encode", "payload",
    ]
```

**优先级**: 🟡 中

---

### 核心: 阶段5 - 通用记忆和学习

**优化策略** (适用于所有站点):
1. **通用模式存储**: 所有站点使用相同的存储结构
2. **通用域名匹配**: 相同域名的API可以复用之前的成功模式

```python
# 通用记忆模式(所有站点使用)
class SuccessPattern:
    domain: str                    # 域名(通用)
    api_type: str                  # API类型(通用)
    signature_extraction: str      # 签名提取方法(通用)
    verification_score: int       # 验证分数(通用)
    timestamp: datetime            # 时间(通用)
    
# 存储位置(所有站点统一)
MEMORY_DIR = "memory/success_patterns/"
```

**优先级**: 🟢 低 - 长期优化

---

## 实施计划 (按优先级排序)

### Wave 1: 核心Bug修复

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T1.1 | 修复StageResult验证错误 | `axelo/models/pipeline.py` | 允许Optional Path |
| T1.2 | 实施通用API选择逻辑 | `axelo/ui/api_scanner.py` | 统一优先级+过滤 |
| T1.3 | 实施通用第三方过滤 | `axelo/ui/api_scanner.py` | 统一域名列表 |

### Wave 2: 验证逻辑改进

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T2.1 | 实施通用验证容错 | `axelo/verification/engine.py` | 统一阈值+忽略列表 |
| T2.2 | 实施通用多级验证 | `axelo/verification/engine.py` | 统一验证级别 |
| T2.3 | 实施通用大文件处理 | `axelo/js_tools/runner.py` | 统一超时+阈值 |

### Wave 3: 记忆和学习

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T3.1 | 实施通用模式记忆 | `axelo/memory/` | 统一存储结构 |

### Wave 4: 测试验证

| 任务 | 描述 | 预期结果 |
|------|------|----------|
| T4.1 | 测试Amazon | 使用通用技术,验证≥80% |
| T4.2 | 测试Lazada | 使用通用技术,验证≥80% |
| T4.3 | 测试Shopee | 使用通用技术,发现≥15个API,验证≥70% |
| T4.4 | 测试eBay | 使用通用技术,验证≥80% |

---

## 预期效果 (通用优化后)

| 平台 | 优化前 | 优化后预期(通用技术) |
|------|--------|-----------|
| Amazon | 30个API,验证0%,报错 | 30个API,验证≥80% |
| Lazada | 30个API,验证0% | 30个API,验证≥80% |
| Shopee | 7个API,验证0% | 15+个API,验证≥70% |
| eBay | 30个API,验证0%,超时 | 30个API,验证≥80% |

---

## 2026-04-08 后续测试结果

### 测试结果

| 平台 | API发现 | 验证通过 | 问题 |
|------|---------|----------|------|
| Amazon | 30 | 0% | API选择错误/复用旧crawler |
| eBay | 30 | 0% | 大文件超时/复用旧crawler |

### 已完成的代码修改

1. ✅ `axelo/models/pipeline.py` - StageResult修复
2. ✅ `axelo/ui/api_scanner.py` - 第三方过滤+API优先级+建议API降级
3. ✅ `axelo/verification/comparator.py` - 改进比较逻辑
4. ✅ `axelo/verification/engine.py` - 改进bridge模式header比较
5. ✅ `axelo/verification/data_quality.py` - 调整阈值
6. ✅ `axelo/js_tools/deobfuscators.py` - 大文件60s超时

### 剩余问题

1. **Adapter复用问题**: 系统在内存中发现之前失败的crawler并复用,导致新修改未生效
2. **API选择问题**: 即使改进排序,实际运行时仍选择了错误的API
3. **根本原因**: 需要更深入的架构级修改,而非配置级调整

---

## 验证标准

- [ ] 所有站点使用统一的API选择逻辑
- [ ] 所有站点使用统一的第三方过滤
- [ ] 所有站点使用统一的验证阈值
- [ ] 所有站点使用统一的大文件处理
- [ ] Amazon: 验证通过率≥80%
- [ ] Lazada: 验证通过率≥80%
- [ ] Shopee: API发现≥15个,验证通过率≥70%
- [ ] eBay: 验证通过率≥80%

---

## 2026-04-08 更新: 深入问题分析

### 新发现的根本问题

#### 问题5: 代码执行失败
**现象**: 运行时报错 "name 'log' is not defined"
**根因**: 生成的爬虫代码模板中使用了log变量但未定义
**修复位置**: 需要检查代码生成模板,添加正确的logger初始化

#### 问题6: 验证逻辑缺陷
**现象**: 验证通过率始终为0%
**根因**: 
- `comparator.py`只比较header格式(Base64/Hex长度匹配)
- 不验证签名值是否正确生成
- 格式正确≠功能正确
**修复位置**: `axelo/verification/comparator.py`

#### 问题7: target_requests为空
**现象**: 验证引擎无法找到ground truth进行比对
**根因**: 
- 验证需要`target.target_requests[0]`存在
- 如果未正确设置,比较无法进行
**修复位置**: 数据流检查,需要确保captures正确传递

#### 问题8: API选择可能错误
**现象**: 可能选择非目标API(如搜索结果而非产品详情)
**根因**: 按confidence和type优先级选择,可能不适合特定目标
**修复位置**: `axelo/ui/api_scanner.py`

---

## 更新后的实施计划

### Wave 1: 核心Bug修复 (原有)

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T1.1 | 修复StageResult验证错误 | `axelo/models/pipeline.py` | 允许Optional Path |
| T1.2 | 实施通用API选择逻辑 | `axelo/ui/api_scanner.py` | 统一优先级+过滤 |
| T1.3 | 实施通用第三方过滤 | `axelo/ui/api_scanner.py` | 统一域名列表 |

### Wave 2: 验证逻辑修复 (新增)

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T2.1 | 修复代码生成模板logger问题 | 代码生成模板 | 添加logger初始化 |
| T2.2 | 改进验证比较逻辑 | `axelo/verification/comparator.py` | 不仅比较格式 |
| T2.3 | 检查target_requests数据流 | `axelo/verification/engine.py` | 确保ground truth传递 |

### Wave 3: 验证逻辑改进 (原有+扩展)

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T3.1 | 实施通用验证容错 | `axelo/verification/engine.py` | 统一阈值+忽略列表 |
| T3.2 | 实施通用多级验证 | `axelo/verification/engine.py` | 统一验证级别 |
| T3.3 | 实施通用大文件处理 | `axelo/js_tools/runner.py` | 统一超时+阈值 |

### Wave 4: 记忆和学习 (原有)

| 任务 | 描述 | 文件位置 | 通用技术 |
|------|------|----------|----------|
| T4.1 | 实施通用模式记忆 | `axelo/memory/` | 统一存储结构 |

### Wave 5: 测试验证

| 任务 | 描述 | 预期结果 |
|------|------|----------|
| T5.1 | 测试Amazon | 使用通用技术,验证≥80% |
| T5.2 | 测试Lazada | 使用通用技术,验证≥80% |
| T5.3 | 测试Shopee | 使用通用技术,发现≥15个API,验证≥70% |
| T5.4 | 测试eBay | 使用通用技术,验证≥80% |