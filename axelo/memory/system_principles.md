# Axelo System Core Principles

This file contains the fundamental principles that govern the Axelo system.
All development must adhere to these principles.

---

## 1. No Site-Specific Micro-Tuning (禁止站点特定微调)

**PRINCIPLE**: Never add code that specifically handles individual websites (Amazon, Shopee, Lazada, eBay, JD, Taobao, etc.)

**RULE**:
- ❌ FORBIDDEN: `if "amazon" in url: ...` or `elif "shopee": ...`
- ✅ ALLOWED: Generic algorithms that work for all sites
- ✅ ALLOWED: Configuration data (JSON/YAML) loaded at runtime

**IMPLEMENTATION**:
- All site-specific data must be externalized to data files (JSON/YAML)
- Site detection must use generic pattern matching
- All browser parameters must be site-agnostic

---

## 2. Model Priority Chain (模型优先级链)

**PRIORITY ORDER**:
1. **Primary**: DeepSeek V3 (`deepseek-chat`)
2. **Secondary**: DeepSeek R1 (`deepseek-reasoner`)
3. **Tertiary**: Claude Opus 4.6 (`claude-opus-4-6-20251105`)

**FALLBACK LOGIC**:
```
try DeepSeek V3
except (rate_limit, quota_error, timeout):
    try DeepSeek R1
    except (rate_limit, quota_error, timeout):
        try Claude Opus 4.6
        except:
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

**PRINCIPLE**: All site-specific data must be externalized to configuration files.

**IMPLEMENTATION**:
- Site profiles in `axelo/data/site_profiles.json`
- URL patterns in configuration, not code
- Algorithm selection based on generic heuristics

---

## Version History

- v1.0 (2026-04-07): Initial principles documented