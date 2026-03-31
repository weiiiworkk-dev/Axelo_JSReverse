from __future__ import annotations
from axelo.models.target import BrowserProfile

# 预置指纹配置
PROFILES: dict[str, BrowserProfile] = {
    "default": BrowserProfile(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        viewport_width=1920,
        viewport_height=1080,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        stealth=True,
    ),
    "mobile": BrowserProfile(
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        viewport_width=390,
        viewport_height=844,
        locale="zh-CN",
        timezone="Asia/Shanghai",
        stealth=True,
    ),
}

# 反检测注入脚本（覆盖 webdriver 特征）
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : originalQuery(parameters);
"""
