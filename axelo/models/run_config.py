from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AntiBotType(str, Enum):
    CLOUDFLARE = "cloudflare"
    DATADOME = "datadome"
    AKAMAI = "akamai"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class OutputFormat(str, Enum):
    JSON_FILE = "json_file"
    CSV = "csv"
    PRINT = "print"
    CUSTOM = "custom"


class CrawlRate(str, Enum):
    CONSERVATIVE = "conservative"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"


class RunMode(str, Enum):
    INTERACTIVE = "interactive"
    AUTO = "auto"
    MANUAL = "manual"


class RunConfig(BaseModel):
    """Canonical runtime input shared by wizard and CLI."""

    url: str
    goal: str
    mode_name: RunMode = RunMode.INTERACTIVE
    budget_usd: float = 2.0

    known_endpoint: str = ""
    antibot_type: AntiBotType = AntiBotType.UNKNOWN
    requires_login: bool | None = None
    output_format: OutputFormat = OutputFormat.PRINT
    crawl_rate: CrawlRate = CrawlRate.STANDARD

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return value

    @field_validator("goal")
    @classmethod
    def _validate_goal(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("goal cannot be empty")
        return value

    @field_validator("known_endpoint")
    @classmethod
    def _normalize_endpoint(cls, value: str) -> str:
        return value.strip()

    @field_validator("budget_usd")
    @classmethod
    def _validate_budget(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("budget_usd must be > 0")
        return float(value)

    def orchestrator_kwargs(self) -> dict:
        return {
            "url": self.url,
            "goal": self.goal,
            "mode_name": self.mode_name.value,
            "budget_usd": self.budget_usd,
            "known_endpoint": self.known_endpoint,
            "antibot_type": self.antibot_type.value,
            "requires_login": self.requires_login,
            "output_format": self.output_format.value,
            "crawl_rate": self.crawl_rate.value,
        }

