from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXELO_", env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    model: str = "claude-opus-4-6"
    workspace: Path = Path("./workspace")
    node_bin: str = "node"
    browser: str = "chromium"
    headless: bool = True
    log_level: str = "info"

    @property
    def sessions_dir(self) -> Path:
        return self.workspace / "sessions"

    @property
    def cache_dir(self) -> Path:
        return self.workspace / "cache"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id


settings = Settings()
