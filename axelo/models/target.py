from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class RequestCapture(BaseModel):
    """捕获的单条网络请求"""
    url: str
    method: str
    request_headers: dict[str, str] = {}
    request_body: bytes | None = None
    response_status: int = 0
    response_headers: dict[str, str] = {}
    response_body: bytes | None = None
    timestamp: float = 0.0
    initiator: Literal["fetch", "xhr", "script", "navigation", "other"] = "other"
    call_stack: list[str] = []
    # 分析后填充
    is_target: bool = False
    token_fields: list[str] = []  # 疑似含有token的请求头/body字段名


class BrowserProfile(BaseModel):
    """浏览器指纹配置"""
    user_agent: str = ""
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    extra_headers: dict[str, str] = {}
    stealth: bool = True  # 是否注入反检测脚本


class TargetSite(BaseModel):
    """逆向目标站点"""
    url: str
    session_id: str
    interaction_goal: str  # 例："爬取搜索结果数据"
    created_at: datetime = Field(default_factory=datetime.now)
    browser_profile: BrowserProfile = Field(default_factory=BrowserProfile)
    captured_requests: list[RequestCapture] = []
    target_requests: list[RequestCapture] = []  # 人工/AI确认后的逆向目标请求
    js_urls: list[str] = []  # 页面上发现的所有JS资源URL

    # ── 用户在向导中提供的上下文（影响AI分析策略和生成代码） ──
    known_endpoint: str = ""
    # 用户已知的 API 接口路径（如 /api/search），空串表示需要自动发现

    antibot_type: str = "unknown"
    # 反爬虫防护类型：cloudflare / datadome / akamai / custom / unknown

    requires_login: bool | None = None
    # 是否需要登录态：True=需要Cookie / False=匿名接口 / None=不确定

    output_format: str = "print"
    # 爬虫输出格式：json_file / csv / print / custom

    crawl_rate: str = "standard"
    # 爬取频率偏好：conservative(3s间隔) / standard(1s间隔) / aggressive(无延迟)
