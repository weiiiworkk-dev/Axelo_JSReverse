from pathlib import Path
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WORKSPACE = _PROJECT_ROOT / "workspace"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXELO_", env_file=str(_PROJECT_ROOT / ".env"), extra="ignore")

    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AXELO_ANTHROPIC_API_KEY"),
    )
    model: str = "claude-opus-4-6"
    workspace: Path = _DEFAULT_WORKSPACE
    sessions_root: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("AXELO_SESSIONS_DIR", "AXELO_SESSIONS_ROOT"),
    )
    node_bin: str = "node"
    browser: str = "chromium"
    headless: bool = True
    log_level: str = "info"
    max_dynamic_retries: int = 2
    verification_subprocess_timeout_sec: float = 15.0
    bundle_download_byte_cap_kb: int = 1024
    ast_extract_timeout_sec: float = 20.0
    platform_mode: str = "local"
    platform_database_url: str = ""
    platform_environment: str = "dev"
    platform_region: str = "global"
    control_api_host: str = "127.0.0.1"
    control_api_port: int = 8787
    platform_poll_interval_sec: float = 1.0

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
    def has_anthropic_api_key(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id


settings = Settings()
