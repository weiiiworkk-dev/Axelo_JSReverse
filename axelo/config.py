from pathlib import Path
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from axelo.utils.session_catalog import session_dir_for_id

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "workspace"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXELO_", env_file=str(_PROJECT_ROOT / ".env"), extra="ignore")

    deepseek_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "AXELO_DEEPSEEK_API_KEY"),
    )
    model: str = "deepseek-chat"
    workspace: Path = _DEFAULT_WORKSPACE
    sessions_root: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("AXELO_SESSIONS_DIR", "AXELO_SESSIONS_ROOT"),
    )
    node_bin: str = "node"
    browser: str = "chromium"
    headless: bool = True
    log_level: str = "info"
    verification_subprocess_timeout_sec: float = 60.0
    # === 大幅度增强反爬机制配置 ===
    # 动态分析阶段页面等待时间(毫秒)
    dynamic_analysis_wait_ms: int = 5000
    # 动态分析阶段最大重试次数 - 跳过动态分析
    dynamic_analysis_max_attempts: int = 0
    # 动态分析阶段重试初始延迟(毫秒)
    dynamic_analysis_retry_initial_delay_ms: int = 1000
    # 是否启用页面交互模拟触发懒加载
    dynamic_analysis_interaction_enabled: bool = False
    # 动态分析阶段最大等待超时(秒) - 快速失败
    dynamic_analysis_timeout_sec: float = 10.0
    # 启用新版无头模式 (更难被检测)
    enable_new_headless_mode: bool = True
    # 反爬重试最大次数
    anti_bot_max_retries: int = 1
    # 反爬重试初始延迟(秒)
    anti_bot_retry_initial_delay_sec: float = 1.0
    # 反爬重试最大延迟(秒)
    anti_bot_retry_max_delay_sec: float = 5.0
    # 启用JavaScript层反检测
    enable_js_anti_detection: bool = True
    # 禁用headful模式
    enable_headful_fallback: bool = False
    # Headful模式超时(秒)
    headful_timeout_sec: float = 15.0
    # === 结束增强配置 ===
    # === 增强Crawl等待配置 ===
    # 页面导航后默认等待时间(毫秒) - 增强到10秒以等待动态内容
    crawl_default_wait_ms: int = 10000
    # 动态内容加载最大等待时间(毫秒)
    crawl_max_wait_ms: int = 30000
    # 是否启用智能等待策略
    adaptive_wait_enabled: bool = True
    # === 结束增强配置 ===
    max_dynamic_retries: int = 2
    max_sessions_per_domain: int = 50
    bundle_download_byte_cap_kb: int = 1024
    ast_extract_timeout_sec: float = 20.0
    transport_adapter: str = "curl_cffi"  # "curl_cffi" | "httpx"
    browser_channel: str = ""              # "" = Chromium; "chrome" = system Google Chrome
    curl_cffi_impersonate: str = "chrome124"
    challenge_resolution_enabled: bool = True
    challenge_resolution_timeout_sec: float = 30.0
    challenge_fail_policy: str = "human_in_loop"  # "warn" | "abort" | "human_in_loop"
    max_challenge_retries: int = 2
    knowledge_retention_days: int = 30
    # Cap-2: Proxy layer
    proxy_mode: str = "direct"           # "direct" | "static" | "rotating"
    proxy_url: str = ""                  # "http://user:pass@host:port"
    proxy_rotation_n: int = 10           # rotate after N requests
    # Cap-3: Headful escalation
    headful_on_challenge_fail: bool = False
    headful_mode: str = "hidden"         # "hidden" | "visible" | "virtual"
    # API-only 模式：只逆向有保护信号的 API 端点（签名/Token/Nonce），跳过无签名公开接口
    api_only_mode: bool = False
    platform_mode: str = "local"
    platform_database_url: str = ""
    platform_environment: str = "dev"
    platform_region: str = "global"
    control_api_host: str = "127.0.0.1"
    control_api_port: int = 8787
    platform_poll_interval_sec: float = 1.0
    # === 增强验证配置 ===
    # 反爬错误码识别模式(正则表达式列表)
    verification_antibot_patterns: list[str] = [
        r"error[_\s]?code[_\s]?9[0]{3,}",  # 90309999, 90000000+ style errors
        r"anti[_-]?bot",
        r"captcha",
        r"challenge",
        r"blocked",
        r"forbidden",
        r"rate[_\s]?limit",
        r"too[_\s]?many[_\s]?requests",
        r"403",
        r"429",
        r"access[_\s]?denied",
        r"please[_\s]?verify",
        r"robot[_\s]?check",
    ]
    # 反爬响应特征字段(检测这些字段表示反爬)
    verification_antibot_fields: list[str] = [
        "error",
        "error_code",
        "error_msg",
        "message",
        "code",
        "status",
        "success",
    ]
    # === 结束增强配置 ===

    @field_validator("workspace", "sessions_root", mode="before")
    @classmethod
    def _resolve_project_relative_paths(cls, value):
        if value in (None, ""):
            return None if value is None else value
        path = Path(value)
        if path.is_absolute():
            return path
        return (_PROJECT_ROOT / path).resolve()

    @property
    def sessions_dir(self) -> Path:
        if self.sessions_root is not None:
            return Path(self.sessions_root)
        return self.workspace / "sessions"

    @property
    def cache_dir(self) -> Path:
        return self.workspace / "cache"

    @property
    def platform_dir(self) -> Path:
        return self.workspace / "platform"

    @property
    def platform_event_dir(self) -> Path:
        return self.platform_dir / "events"

    @property
    def platform_object_store_dir(self) -> Path:
        return self.platform_dir / "object_store"

    @property
    def platform_warehouse_dir(self) -> Path:
        return self.platform_dir / "warehouse"

    @property
    def has_deepseek_api_key(self) -> bool:
        return bool(self.deepseek_api_key and self.deepseek_api_key.strip())

    def session_dir(self, session_id: str) -> Path:
        return session_dir_for_id(self.sessions_dir, session_id)


settings = Settings()
