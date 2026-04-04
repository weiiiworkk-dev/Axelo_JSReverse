from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXELO_", env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AXELO_ANTHROPIC_API_KEY"),
    )
    model: str = "claude-opus-4-6"
    workspace: Path = Path("./workspace")
    node_bin: str = "node"
    browser: str = "chromium"
    headless: bool = True
    log_level: str = "info"
    max_dynamic_retries: int = 2
    verification_subprocess_timeout_sec: float = 15.0
    bundle_download_byte_cap_kb: int = 1024
    ast_extract_timeout_sec: float = 20.0

    @property
    def sessions_dir(self) -> Path:
        return self.workspace / "sessions"

    @property
    def cache_dir(self) -> Path:
        return self.workspace / "cache"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id


settings = Settings()
