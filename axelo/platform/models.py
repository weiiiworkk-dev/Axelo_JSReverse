from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import hashlib
import uuid

from pydantic import BaseModel, Field, model_validator


def site_key_from_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return parsed.netloc.lower()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def frontier_hash(site_key: str, canonical_url: str) -> str:
    payload = f"{site_key.lower()}|{canonical_url}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8]}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class PlatformMode(str, Enum):
    LOCAL = "local"
    CLUSTER = "cluster"


class JobType(str, Enum):
    REVERSE = "reverse"
    CRAWL = "crawl"
    BRIDGE = "bridge"
    SESSION_REFRESH = "session_refresh"


class WorkerType(str, Enum):
    REVERSE = "reverse-worker"
    CRAWL = "crawl-worker"
    BRIDGE = "bridge-worker"
    SESSION_REFRESH = "session-refresh-worker"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELEGATED = "delegated"
    CANCELLED = "cancelled"


class FrontierStatus(str, Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COOLING = "cooling"


class AccountStatus(str, Enum):
    NEW = "new"
    WARMING = "warming"
    ACTIVE = "active"
    COOLING = "cooling"
    CHALLENGED = "challenged"
    LOCKED = "locked"
    RETIRED = "retired"


class ProxyStatus(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    COOLING = "cooling"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class LeaseStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class ResourceType(str, Enum):
    ACCOUNT = "account"
    PROXY = "proxy"


class BaseJobSpec(BaseModel):
    site_key: str = ""
    queue: str = "default"
    region: str = "global"
    priority: int = 100
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReverseJobSpec(BaseJobSpec):
    url: str
    goal: str = "分析并复现请求签名/Token 生成逻辑"
    target_hint: str = ""
    use_case: str = "research"
    authorization_status: str = "pending"
    replay_mode: str = "discover_only"
    known_endpoint: str = ""
    antibot_type: str = "unknown"
    requires_login: bool | None = None
    output_format: str = "json_file"
    crawl_rate: str = "standard"
    browser_profile_name: str = "default"
    budget_usd: float = 2.0

    @model_validator(mode="after")
    def _fill_site_key(self) -> "ReverseJobSpec":
        if not self.site_key:
            self.site_key = site_key_from_url(self.url)
        return self


class CrawlJobSpec(BaseJobSpec):
    adapter_version: str = ""
    site_url: str
    source_url: str = ""
    frontier_item_id: str = ""
    action: str = "page"
    crawl_kwargs: dict[str, Any] = Field(default_factory=dict)
    output_format: str = "json_file"
    dataset_name: str = "default"
    schema_version: str = "v1"
    account_id: str = ""
    proxy_id: str = ""
    extractor_version: str = "v1"

    @model_validator(mode="after")
    def _fill_site_fields(self) -> "CrawlJobSpec":
        if not self.site_key:
            self.site_key = site_key_from_url(self.site_url or self.source_url)
        if not self.source_url:
            self.source_url = self.site_url
        return self


class BridgeJobSpec(CrawlJobSpec):
    parent_crawl_job_id: str = ""


class SessionRefreshJobSpec(BaseJobSpec):
    account_id: str
    refresh_url: str
    browser_profile_name: str = "default"
    expected_domain: str = ""

    @model_validator(mode="after")
    def _fill_site_key(self) -> "SessionRefreshJobSpec":
        if not self.site_key:
            self.site_key = site_key_from_url(self.refresh_url)
        return self


class FrontierSeedRequest(BaseModel):
    urls: list[str]
    site_key: str = ""
    adapter_version: str = ""
    priority: int = 100
    depth: int = 0
    discovered_from: str = ""
    region: str = "global"
    request_kwargs: dict[str, Any] = Field(default_factory=dict)


class FrontierItem(BaseModel):
    item_id: str = Field(default_factory=lambda: new_id("frontier"))
    site_key: str
    canonical_url: str
    url_hash: str
    priority: int = 100
    depth: int = 0
    discovered_from: str = ""
    status: FrontierStatus = FrontierStatus.DISCOVERED
    adapter_version: str = ""
    next_eligible_at: datetime = Field(default_factory=utc_now)
    last_result: str = ""
    region: str = "global"
    request_kwargs: dict[str, Any] = Field(default_factory=dict)


class AdapterVersion(BaseModel):
    site_key: str
    version: str
    output_mode: str
    crawler_script_ref: str
    bridge_server_ref: str = ""
    manifest_ref: str = ""
    signature_spec: dict[str, Any] | None = None
    verification_report_ref: str = ""
    compatibility_tags: list[str] = Field(default_factory=list)
    source_reverse_job_id: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    verified_at: datetime | None = None


class AccountRecord(BaseModel):
    account_id: str = Field(default_factory=lambda: new_id("acct"))
    site_key: str
    credential_ref: str
    status: AccountStatus = AccountStatus.NEW
    session_state_ref: str = ""
    risk_score: float = 0.0
    last_login_at: datetime | None = None
    last_refresh_at: datetime | None = None
    warmup_phase: str = ""
    owner_policy: dict[str, Any] = Field(default_factory=dict)


class ProxyRecord(BaseModel):
    proxy_id: str = Field(default_factory=lambda: new_id("proxy"))
    provider: str
    region: str
    protocol: str = "http"
    endpoint: str = ""
    auth: str = ""
    quality_score: float = 1.0
    ban_score: float = 0.0
    sticky_capable: bool = False
    supports_browser: bool = False
    status: ProxyStatus = ProxyStatus.NEW


class LeaseRecord(BaseModel):
    lease_id: str = Field(default_factory=lambda: new_id("lease"))
    resource_type: ResourceType
    resource_id: str
    job_type: JobType
    job_id: str
    site_key: str
    region: str = "global"
    status: LeaseStatus = LeaseStatus.ACTIVE
    acquired_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(default_factory=lambda: utc_now() + timedelta(minutes=15))
    released_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResultEnvelope(BaseModel):
    result_id: str = Field(default_factory=lambda: new_id("result"))
    job_id: str
    site_key: str
    adapter_version: str
    account_id: str = ""
    proxy_id: str = ""
    request_fingerprint: str = ""
    source_url: str = ""
    response_status: int = 0
    schema_version: str = "v1"
    raw_payload_ref: str = ""
    normalized_payload: Any = None
    observed_at: datetime = Field(default_factory=utc_now)
    dataset_name: str = "default"
    extractor_version: str = "v1"


class DatasetSchema(BaseModel):
    dataset_name: str
    version: str
    schema_definition: dict[str, Any]
    extractor_version: str = "v1"
    created_at: datetime = Field(default_factory=utc_now)


class WorkerHeartbeat(BaseModel):
    worker_id: str = Field(default_factory=lambda: new_id("worker"))
    worker_type: WorkerType
    region: str = "global"
    queue_name: str = "default"
    status: str = "healthy"
    details: dict[str, Any] = Field(default_factory=dict)
    last_seen_at: datetime = Field(default_factory=utc_now)


class QueuedJob(BaseModel):
    job_type: JobType
    job_id: str
    site_key: str
    queue: str
    region: str
    priority: int
    status: JobStatus
    spec: ReverseJobSpec | CrawlJobSpec | BridgeJobSpec | SessionRefreshJobSpec
    parent_job_id: str = ""
    created_at: datetime = Field(default_factory=utc_now)
