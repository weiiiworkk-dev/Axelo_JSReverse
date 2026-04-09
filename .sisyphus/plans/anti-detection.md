# Anti-Detection Enhancement Plan

## 1. Problem Statement

**Current Issue**: Amazon and other high-protection websites block automated browser access, causing:
- Navigation timeouts (30s → 60s still fails)
- Anti-bot detection triggers CAPTCHA or blocking pages
- API scanning fails before capturing any requests

**Root Cause**: Playwright's default automation flags are detectable:
- `navigator.webdriver` = true
- Chrome runtime variables exposed
- Automation-controlled browser特征
- Consistent viewport / User-Agent patterns

---

## 2. Goals

1. **Primary**: Successfully scan Amazon/anti-bot protected websites
2. **Secondary**: Improve detection resistance for all target websites
3. **Tertiary**: Maintain performance (scan time < 2 minutes)

---

## 3. Technical Analysis

### 3.1 Detection Vectors

| Vector | Current State | Risk Level |
|--------|---------------|------------|
| `navigator.webdriver` | Partially masked | 🔴 High |
| `window.chrome` | Not set | 🔴 High |
| Automation plugins | Not blocked | 🔴 High |
| User-Agent | Default Chrome | 🟡 Medium |
| Screen resolution | Fixed 1920x1080 | 🟡 Medium |
| Mouse movements | None (instant navigation) | 🔴 High |
| Keyboard patterns | None | 🟡 Medium |
| Canvas/WebGL | Not randomized | 🟡 Medium |
| Timezone | System default | 🟢 Low |
| Language | System default | 🟢 Low |

### 3.2 Existing Anti-Detection Code

Current implementation in `axelo/browser/driver.py`:
```python
# Already implemented:
--disable-blink-features=AutomationControlled
--disable-infobars
--no-first-run
--no-default-browser-check
```

Current in `axelo/browser/simulation.py`:
- `navigator.webdriver` = false
- `window.chrome` = defined
- Basic runtime simulation

**Gap**: Missing advanced features (mouse, keyboard, canvas, etc.)

---

## 4. Implementation Plan

### Phase 1: Browser Injection Enhancement

#### T1.1: Enhance Simulation Script (simulation.py)

**Task**: Expand `render_simulation_init_script()` with:
- [x] Override `navigator.plugins` (return real Chrome plugins)
- [x] Override `navigator.languages` (match User-Agent)
- [x] Override `navigator.hardwareConcurrency`
- [x] Override `navigator.deviceMemory`
- [x] Add fake Canvas fingerprint
- [x] Add fake WebGL renderer
- [x] Override `screen` properties
- [x] Override `window.innerWidth/Height` to match viewport

**Status**: ✅ ALREADY IMPLEMENTED in existing simulation.py

#### T1.2: Add Stealth Plugins

**Task**: Add undetected Playwright stealth plugins:
- [ ] Install `playwright-stealth` or implement custom
- [x] Apply stealth patches on browser launch

**Status**: ✅ Partially implemented (launch args enhanced)

---

### Phase 2: Behavior Simulation

#### T2.1: Mouse Movement Simulation

**Task**: Add realistic mouse movements:
- [x] Bezier curve-based random paths (already in simulation.py)
- [x] Variable speed (fast/slow movements)
- [x] Stopovers at interactive elements (hover_pause_ms)
- [x] Scroll behavior with momentum

**Status**: ✅ ALREADY IMPLEMENTED in simulation.py

#### T2.2: Keyboard Input Simulation

**Task**: Add realistic typing patterns:
- [ ] Variable typing speed (30-80 WPM)
- [ ] Random correction (backspace)
- [ ] Random pauses between keystrokes

#### T2.3: Human-like Scroll

**Task**: Implement human-like scrolling:
- [x] Incremental scroll with variable step sizes
- [x] Pause at content-rich sections
- [x] Back-and-forth micro-movements

**Status**: ✅ ALREADY IMPLEMENTED

---

### Phase 3: Request Pattern Optimization

#### T3.1: Randomize Request Headers

**Task**: Add request header randomization:
- [x] TLS headers already in driver.py (build_tls_extra_headers)
- [x] `Accept-Language` permutation (via profile)

**Status**: ✅ Partially implemented

#### T3.2: Add Request Delays

**Task**: Add realistic request delays:
- [x] Random delay between requests (100-500ms)
- [ ] Burst prevention (max 3 concurrent)
- [ ] Time-of-day variation

**Status**: ✅ Implemented in api_scanner.py

---

### Phase 4: Profile Enhancement

#### T4.1: Multiple Browser Profiles

**Task**: Create diverse browser profiles:
- [x] Chrome (Windows 10/11)
- [x] Edge (Windows 10/11)
- [x] Safari (macOS)
- [x] Firefox (Windows/Linux)
- [x] Each with unique viewport, timezone, language

**Status**: ✅ COMPLETED - Added 4 new profiles:
- `chrome_windows_11` - Chrome on Windows 11, en-US
- `edge_windows_10` - Edge on Windows 10, en-GB  
- `safari_macos` - Safari on macOS
- `firefox_windows` - Firefox on Windows

#### T4.2: Profile Rotation

**Task**: Implement profile rotation:
- [x] Random profile selection per scan (`get_stealth_profile()`)
- [x] Session-based sticky assignment
- [ ] Failure-based blacklist

**Status**: ✅ Implemented - Added `get_random_profile()` and `get_stealth_profile()`

---

### Phase 5: Advanced Evasion

#### T5.1: Proxy Integration

**Task**: Add proxy support:
- [ ] HTTP/HTTPS proxy configuration
- [ ] Residential proxy integration
- [ ] Proxy rotation per attempt
- [ ] Connection health check

**Files**: `axelo/browser/driver.py`, `axelo/config.py`

#### T5.2: CAPTCHA Handling

**Task**: Add CAPTCHA detection and handling:
- [ ] Detect CAPTCHA pages (image/audio challenge)
- [ ] Optional 2Captche/Anti-Captcha integration
- [ ] Fallback to manual intervention
- [ ] Alert user when CAPTCHA detected

**Files**: `axelo/browser/challenge_monitor.py` (new)

#### T5.3: TLS Fingerprint

**Task**: Optimize TLS fingerprint:
- [ ] Match Chrome's TLS ciphers
- [ ] ALPN protocol matching
- [ ] SNI consistency

**Files**: `axelo/browser/tls_profile.py`

---

## 5. Implementation Priority

| Priority | Task | Status | Effort | Impact |
|----------|------|--------|--------|--------|
| P0 | T1.1 - Simulation Enhancement | ✅ Already Done | - | 🔴 High |
| P1 | T2.1 - Mouse Simulation | ✅ Already Done | - | 🔴 High |
| P1 | T1.2 - Stealth Launch Args | ✅ Completed | Low | 🔴 High |
| P2 | T4.1 - Multiple Profiles | ✅ Completed | Medium | 🟡 Medium |
| P2 | T4.2 - Profile Rotation | ✅ Completed | Low | 🟡 Medium |
| P2 | T2.3 - Human Scroll | ✅ Already Done | - | 🟡 Medium |
| P3 | T3.1 - Header Randomization | ✅ Partially Done | - | 🟡 Medium |
| P3 | T5.1 - Proxy Support | ⏳ Pending | High | 🟢 Low |
| P4 | T5.2 - CAPTCHA Handling | ⏳ Pending | High | 🟢 Low |

---

## 6. Estimated Timeline

- **Phase 1**: 0 hours (already implemented)
- **Phase 2**: 0 hours (already implemented)  
- **Phase 3**: 0 hours (partially done)
- **Phase 4**: 1 hour ✅ COMPLETED
- **Phase 5**: Pending (optional advanced features)

**Total**: ~1 hour for Phase 4 (profiles + rotation)

---

## 7. Verification Criteria

### Success Metrics

1. **Amazon Test**: Successfully load Amazon homepage without timeout/blocking
2. **API Discovery**: Capture ≥10 API requests from Amazon
3. **Performance**: Total scan time < 2 minutes
4. **Compatibility**: No regression on previously working sites (bilibili, jd.com)

### Test Commands

```bash
# Test 1: Amazon
axelo amazon

# Test 2: Previously working sites
axelo bilibili.com
axelo jd.com
```

---

## 8. COMPLETED CHANGES

### Files Modified

| File | Change |
|------|--------|
| `axelo/browser/profiles.py` | Added 4 new stealth profiles + random selection functions |
| `axelo/browser/driver.py` | Enhanced launch args (20+ anti-detection flags) |
| `axelo/ui/api_scanner.py` | Using stealth profile + retry mechanism + human-like behavior |

### New Features

1. **Multiple Browser Profiles**:
   - `chrome_windows_11` - Chrome on Windows 11, en-US timezone
   - `edge_windows_10` - Edge on Windows 10, UK timezone
   - `safari_macos` - Safari on macOS
   - `firefox_windows` - Firefox on Windows

2. **Profile Selection**:
   - `get_stealth_profile()` - Random stealth profile
   - `get_random_profile()` - Random any profile

3. **Enhanced Browser Launch**:
   - 20+ Chrome flags for anti-detection
   - Disabled various telemetry/background features
   - Single process mode

4. **Human-like Behavior in API Scanner**:
   - Random viewport size
   - Random delays (1-3 seconds)
   - Random scroll simulation
   - 2x retry mechanism
   - domcontentloaded instead of networkidle

---

## 9. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-------------|
| Amazon permanently blocks | Medium | High | Proxy + CAPTCHA fallback |
| Over-complication | Medium | Medium | Stick to completed tasks only |
| Performance degradation | Low | Medium | Monitor scan time |
| Browser crash | Low | Low | Graceful error handling |

---

## 9. Budget

- **AI Tokens**: ~5000 tokens (planning + implementation)
- **Proxy Costs**: Optional (~$10/month for residential)
- **CAPTCHA Service**: Optional (~$15/month pay-per-use)

---

## 10. Next Steps

1. **Approve Plan** → Start Phase 1 (T1.1)
2. **Partial Approve** → Start P0 tasks only
3. **Request Changes** → Provide feedback

---

**Plan Version**: 1.0  
**Created**: 2026-04-06  
**Status**: Pending Approval
