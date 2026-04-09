# Axelo System Core Principles

This file contains the fundamental principles that govern the Axelo system.
All development must adhere to these principles.

---

## 1. No Site-Specific Micro-Tuning (禁止站点特定微调)

**PRINCIPLE**: Never add code that specifically handles individual websites (Amazon, Shopee, Lazada, eBay, JD, Taobao, etc.)

**RULE**:
- ❌ FORBIDDEN: `if "brand_x" in url: ...` or `elif "brand_y": ...`
- ❌ FORBIDDEN: Any built-in brand/domain lookup table used to special-case behavior
- ✅ ALLOWED: Generic algorithms that work for all sites
- ✅ ALLOWED: User-provided target URL/domain as plain input

**IMPLEMENTATION**:
- Core tool behavior must be fully site-agnostic
- No hardcoded domain mapping in code paths
- Browser/network parameters must be generic and reusable

---

## 2. Model Priority Chain (模型优先级链)

**PRIORITY ORDER**:
1. **Primary**: DeepSeek V3 (`deepseek-chat`)
2. **Secondary**: DeepSeek R1 (`deepseek-reasoner`)

**FALLBACK LOGIC**:
```
try DeepSeek V3
except (rate_limit, quota_error, timeout):
    try DeepSeek R1
    except (rate_limit, quota_error, timeout):
        raise NoModelsAvailableError
```

---

## 3. Universal Anti-Detection (通用反爬系统)

**PRINCIPLE**: All anti-detection mechanisms must work for all websites without site-specific code.

**REQUIREMENTS**:
- Browser fingerprint randomization (navigator properties)
- Generic timeout configuration
- Universal retry logic
- No site-specific URL handling

---

## 4. Configuration-Driven (配置驱动)

**PRINCIPLE**: Runtime options may be configured, but tool logic must remain generic.

**IMPLEMENTATION**:
- Runtime params come from user input and common defaults
- Avoid domain-specific profiles in runtime decision logic
- Algorithm selection based on generic heuristics

---

## 5. Compliance Note (本次新增)

- Reverse/crawling capability may only be enhanced through universal tools.
- Do not add or preserve any site-specific micro-tuning in router, scanner, toolchain, or memory patterns.

---

## Version History

- v1.0 (2026-04-07): Initial principles documented