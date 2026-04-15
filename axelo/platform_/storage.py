from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

from sqlmodel import Field, SQLModel, Session, create_engine, select

from axelo.platform_.models import (
    AccountRecord,
    AccountStatus,
    AdapterVersion,
    BridgeJobSpec,
    CrawlJobSpec,
    DatasetSchema,
    FrontierItem,
    FrontierStatus,
    JobStatus,
    JobType,
    LeaseRecord,
    LeaseStatus,
    ProxyRecord,
    ProxyStatus,
    QueuedJob,
    ResourceType,
    ResultEnvelope,
    ReverseJobSpec,
    SessionRefreshJobSpec,
    WorkerHeartbeat,
    utc_now,
)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: str, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class JobRowBase(SQLModel, table=False):
    job_id: str = Field(primary_key=True)
    site_key: str = Field(index=True)
    queue: str = Field(default="default", index=True)
    region: str = Field(default="global", index=True)
    priority: int = Field(default=100, index=True)
    status: str = Field(default=JobStatus.QUEUED.value, index=True)
    payload_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    error: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ReverseJobRow(JobRowBase, table=True):
    __tablename__ = "reverse_jobs"


class CrawlJobRow(JobRowBase, table=True):
    __tablename__ = "crawl_jobs"

    adapter_version: str = Field(default="", index=True)
    parent_job_id: str = Field(default="", index=True)


class BridgeJobRow(JobRowBase, table=True):
    __tablename__ = "bridge_jobs"

    adapter_version: str = Field(default="", index=True)
    parent_crawl_job_id: str = Field(default="", index=True)


class SessionRefreshJobRow(JobRowBase, table=True):
    __tablename__ = "session_refresh_jobs"


class FrontierUrlRow(SQLModel, table=True):
    __tablename__ = "frontier_urls"

    item_id: str = Field(primary_key=True)
    site_key: str = Field(index=True)
    canonical_url: str
    url_hash: str = Field(index=True)
    priority: int = Field(default=100, index=True)
    depth: int = 0
    discovered_from: str = ""
    status: str = Field(default=FrontierStatus.DISCOVERED.value, index=True)
    adapter_version: str = ""
    intent_fingerprint: str = Field(default="", index=True)
    dataset_name: str = Field(default="default", index=True)
    next_eligible_at: datetime = Field(default_factory=utc_now, index=True)
    last_result: str = ""
    region: str = Field(default="global", index=True)
    request_kwargs_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class AdapterVersionRow(SQLModel, table=True):
    __tablename__ = "adapter_versions"

    adapter_id: str = Field(primary_key=True)
    site_key: str = Field(index=True)
    version: str = Field(index=True)
    output_mode: str
    adapter_package_version: str = "v1"
    dataset_contract_version: str = "v1"
    intent_fingerprint: str = Field(default="", index=True)
    request_contract_hash: str = Field(default="", index=True)
    family_id: str = Field(default="unknown", index=True)
    crawler_script_ref: str
    bridge_server_ref: str = ""
    manifest_ref: str = ""
    adapter_package_ref: str = ""
    request_contract_json: str = Field(default="null")
    dataset_contract_json: str = Field(default="null")
    capability_profile_json: str = Field(default="null")
    verification_profile_json: str = Field(default="null")
    signature_spec_json: str = Field(default="null")
    verification_report_ref: str = ""
    compatibility_tags_json: str = Field(default="[]")
    source_reverse_job_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    verified_at: datetime | None = None


class AccountRow(SQLModel, table=True):
    __tablename__ = "account_inventory"

    account_id: str = Field(primary_key=True)
    site_key: str = Field(index=True)
    credential_ref: str
    status: str = Field(default=AccountStatus.NEW.value, index=True)
    session_state_ref: str = ""
    risk_score: float = 0.0
    last_login_at: datetime | None = None
    last_refresh_at: datetime | None = None
    warmup_phase: str = ""
    owner_policy_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=utc_now)


class ProxyRow(SQLModel, table=True):
    __tablename__ = "proxy_inventory"

    proxy_id: str = Field(primary_key=True)
    provider: str
    region: str = Field(index=True)
    protocol: str = "http"
    endpoint: str = ""
    auth: str = ""
    quality_score: float = 1.0
    ban_score: float = 0.0
    sticky_capable: bool = False
    supports_browser: bool = False
    status: str = Field(default=ProxyStatus.NEW.value, index=True)
    updated_at: datetime = Field(default_factory=utc_now)


class LeaseRow(SQLModel, table=True):
    __tablename__ = "resource_leases"

    lease_id: str = Field(primary_key=True)
    resource_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    job_type: str = Field(index=True)
    job_id: str = Field(index=True)
    site_key: str = Field(index=True)
    region: str = Field(default="global", index=True)
    status: str = Field(default=LeaseStatus.ACTIVE.value, index=True)
    acquired_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(default_factory=lambda: utc_now() + timedelta(minutes=15), index=True)
    released_at: datetime | None = None
    details_json: str = Field(default="{}")


class WorkerHeartbeatRow(SQLModel, table=True):
    __tablename__ = "worker_heartbeats"

    worker_id: str = Field(primary_key=True)
    worker_type: str = Field(index=True)
    region: str = Field(default="global", index=True)
    queue_name: str = Field(default="default", index=True)
    status: str = "healthy"
    details_json: str = Field(default="{}")
    last_seen_at: datetime = Field(default_factory=utc_now, index=True)


class VerificationRunRow(SQLModel, table=True):
    __tablename__ = "verification_runs"

    verification_id: str = Field(primary_key=True)
    site_key: str = Field(index=True)
    adapter_version: str = Field(default="", index=True)
    reverse_job_id: str = Field(default="", index=True)
    verified: bool = False
    report_ref: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utc_now, index=True)


class ResultEnvelopeRow(SQLModel, table=True):
    __tablename__ = "result_envelopes"

    result_id: str = Field(primary_key=True)
    job_id: str = Field(index=True)
    site_key: str = Field(index=True)
    adapter_version: str = Field(index=True)
    account_id: str = ""
    proxy_id: str = ""
    request_fingerprint: str = Field(default="", index=True)
    source_url: str = ""
    response_status: int = 0
    schema_version: str = "v1"
    dataset_contract_version: str = "v1"
    adapter_package_version: str = "v1"
    raw_payload_ref: str = ""
    normalized_payload_json: str = Field(default="null")
    dataset_name: str = Field(default="default", index=True)
    extractor_version: str = "v1"
    observed_at: datetime = Field(default_factory=utc_now, index=True)
    stored_at: datetime = Field(default_factory=utc_now)


class DatasetSchemaRow(SQLModel, table=True):
    __tablename__ = "dataset_schemas"

    schema_id: str = Field(primary_key=True)
    dataset_name: str = Field(index=True)
    version: str = Field(index=True)
    schema_definition_json: str = Field(default="{}")
    extractor_version: str = "v1"
    created_at: datetime = Field(default_factory=utc_now)


_JOB_ROWS = {
    JobType.REVERSE: ReverseJobRow,
    JobType.CRAWL: CrawlJobRow,
    JobType.BRIDGE: BridgeJobRow,
    JobType.SESSION_REFRESH: SessionRefreshJobRow,
}

_JOB_SPECS = {
    JobType.REVERSE: ReverseJobSpec,
    JobType.CRAWL: CrawlJobSpec,
    JobType.BRIDGE: BridgeJobSpec,
    JobType.SESSION_REFRESH: SessionRefreshJobSpec,
}


class PlatformStore:
    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self._engine = create_engine(database_url, connect_args=connect_args)
        SQLModel.metadata.create_all(self._engine)
        if database_url.startswith("sqlite"):
            self._apply_sqlite_compat_migrations()

    def _apply_sqlite_compat_migrations(self) -> None:
        required_columns = {
            "frontier_urls": {
                "intent_fingerprint": "TEXT DEFAULT ''",
                "dataset_name": "TEXT DEFAULT 'default'",
            },
            "adapter_versions": {
                "adapter_package_version": "TEXT DEFAULT 'v1'",
                "dataset_contract_version": "TEXT DEFAULT 'v1'",
                "intent_fingerprint": "TEXT DEFAULT ''",
                "request_contract_hash": "TEXT DEFAULT ''",
                "family_id": "TEXT DEFAULT 'unknown'",
                "adapter_package_ref": "TEXT DEFAULT ''",
                "request_contract_json": "TEXT DEFAULT 'null'",
                "dataset_contract_json": "TEXT DEFAULT 'null'",
                "capability_profile_json": "TEXT DEFAULT 'null'",
                "verification_profile_json": "TEXT DEFAULT 'null'",
            },
            "result_envelopes": {
                "dataset_contract_version": "TEXT DEFAULT 'v1'",
                "adapter_package_version": "TEXT DEFAULT 'v1'",
            },
        }
        with self._engine.begin() as conn:
            for table_name, columns in required_columns.items():
                existing = {
                    row[1]
                    for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
                }
                for column_name, column_sql in columns.items():
                    if column_name in existing:
                        continue
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def submit_job(
        self,
        job_type: JobType,
        spec: ReverseJobSpec | CrawlJobSpec | BridgeJobSpec | SessionRefreshJobSpec,
    ) -> QueuedJob:
        row_cls = _JOB_ROWS[job_type]
        payload = spec.model_dump(mode="json")
        common = dict(
            job_id=payload.get("job_id") or f"{job_type.value}-{utc_now().strftime('%Y%m%d%H%M%S%f')[:20]}",
            site_key=spec.site_key,
            queue=spec.queue,
            region=spec.region,
            priority=spec.priority,
            status=JobStatus.QUEUED.value,
            payload_json=_json_dumps(payload),
            updated_at=utc_now(),
        )
        if row_cls is CrawlJobRow:
            row = row_cls(**common, adapter_version=getattr(spec, "adapter_version", ""), parent_job_id="")
        elif row_cls is BridgeJobRow:
            row = row_cls(
                **common,
                adapter_version=getattr(spec, "adapter_version", ""),
                parent_crawl_job_id=getattr(spec, "parent_crawl_job_id", ""),
            )
        else:
            row = row_cls(**common)
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
        return self._to_job(job_type, row)

    def list_jobs(self, job_type: JobType) -> list[QueuedJob]:
        row_cls = _JOB_ROWS[job_type]
        with Session(self._engine) as session:
            rows = session.exec(select(row_cls).order_by(row_cls.created_at)).all()
        return [self._to_job(job_type, row) for row in rows]

    def acquire_job(self, job_type: JobType, *, queue: str = "default", region: str = "global") -> QueuedJob | None:
        row_cls = _JOB_ROWS[job_type]
        with Session(self._engine) as session:
            statement = (
                select(row_cls)
                .where(row_cls.status == JobStatus.QUEUED.value)
                .where(row_cls.queue == queue)
                .where(row_cls.region == region)
                .order_by(row_cls.priority, row_cls.created_at)
            )
            row = session.exec(statement).first()
            if row is None:
                return None
            row.status = JobStatus.RUNNING.value
            row.started_at = utc_now()
            row.updated_at = utc_now()
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_job(job_type, row)

    def complete_job(self, job_type: JobType, job_id: str, result: dict[str, Any]) -> None:
        self._update_job(job_type, job_id, JobStatus.COMPLETED, result=result)

    def fail_job(self, job_type: JobType, job_id: str, error: str, result: dict[str, Any] | None = None) -> None:
        self._update_job(job_type, job_id, JobStatus.FAILED, error=error, result=result or {})

    def delegate_job(self, job_type: JobType, job_id: str, child_job_id: str) -> None:
        self._update_job(job_type, job_id, JobStatus.DELEGATED, result={"child_job_id": child_job_id})

    def open_job_exists(self, job_type: JobType, site_key: str) -> bool:
        row_cls = _JOB_ROWS[job_type]
        with Session(self._engine) as session:
            statement = (
                select(row_cls)
                .where(row_cls.site_key == site_key)
                .where(row_cls.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]))
            )
            return session.exec(statement).first() is not None

    def register_adapter_version(self, adapter: AdapterVersion) -> AdapterVersion:
        row = AdapterVersionRow(
            adapter_id=f"{adapter.site_key}:{adapter.version}",
            site_key=adapter.site_key,
            version=adapter.version,
            output_mode=adapter.output_mode,
            adapter_package_version=adapter.adapter_package_version,
            dataset_contract_version=adapter.dataset_contract_version,
            intent_fingerprint=adapter.intent_fingerprint,
            request_contract_hash=adapter.request_contract_hash,
            family_id=adapter.family_id,
            crawler_script_ref=adapter.crawler_script_ref,
            bridge_server_ref=adapter.bridge_server_ref,
            manifest_ref=adapter.manifest_ref,
            adapter_package_ref=adapter.adapter_package_ref,
            request_contract_json=_json_dumps(adapter.request_contract),
            dataset_contract_json=_json_dumps(adapter.dataset_contract),
            capability_profile_json=_json_dumps(adapter.capability_profile),
            verification_profile_json=_json_dumps(adapter.verification_profile),
            signature_spec_json=_json_dumps(adapter.signature_spec),
            verification_report_ref=adapter.verification_report_ref,
            compatibility_tags_json=_json_dumps(adapter.compatibility_tags),
            source_reverse_job_id=adapter.source_reverse_job_id,
            created_at=adapter.created_at,
            verified_at=adapter.verified_at,
        )
        with Session(self._engine) as session:
            existing = session.get(AdapterVersionRow, row.adapter_id)
            if existing is not None:
                for field in (
                    "output_mode",
                    "adapter_package_version",
                    "dataset_contract_version",
                    "intent_fingerprint",
                    "request_contract_hash",
                    "family_id",
                    "crawler_script_ref",
                    "bridge_server_ref",
                    "manifest_ref",
                    "adapter_package_ref",
                    "request_contract_json",
                    "dataset_contract_json",
                    "capability_profile_json",
                    "verification_profile_json",
                    "signature_spec_json",
                    "verification_report_ref",
                    "compatibility_tags_json",
                    "source_reverse_job_id",
                    "created_at",
                    "verified_at",
                ):
                    setattr(existing, field, getattr(row, field))
                session.add(existing)
            else:
                session.add(row)
            session.commit()
        return adapter

    def get_adapter(self, site_key: str, version: str) -> AdapterVersion | None:
        with Session(self._engine) as session:
            statement = select(AdapterVersionRow).where(AdapterVersionRow.site_key == site_key).where(AdapterVersionRow.version == version)
            row = session.exec(statement).first()
        return self._to_adapter(row) if row else None

    def latest_adapter(self, site_key: str) -> AdapterVersion | None:
        with Session(self._engine) as session:
            statement = (
                select(AdapterVersionRow)
                .where(AdapterVersionRow.site_key == site_key)
                .order_by(AdapterVersionRow.verified_at.desc(), AdapterVersionRow.created_at.desc())
            )
            row = session.exec(statement).first()
        return self._to_adapter(row) if row else None

    def list_adapters(self, site_key: str) -> list[AdapterVersion]:
        with Session(self._engine) as session:
            statement = select(AdapterVersionRow).where(AdapterVersionRow.site_key == site_key).order_by(AdapterVersionRow.created_at.desc())
            rows = session.exec(statement).all()
        return [self._to_adapter(row) for row in rows]

    def submit_frontier_items(self, items: list[FrontierItem]) -> list[FrontierItem]:
        saved: list[FrontierItem] = []
        with Session(self._engine) as session:
            for item in items:
                existing = session.exec(
                    select(FrontierUrlRow)
                    .where(FrontierUrlRow.site_key == item.site_key)
                    .where(FrontierUrlRow.url_hash == item.url_hash)
                ).first()
                if existing is not None:
                    if item.priority < existing.priority:
                        existing.priority = item.priority
                    if item.intent_fingerprint and not existing.intent_fingerprint:
                        existing.intent_fingerprint = item.intent_fingerprint
                    if item.dataset_name and existing.dataset_name == "default":
                        existing.dataset_name = item.dataset_name
                    existing.updated_at = utc_now()
                    session.add(existing)
                    saved.append(self._to_frontier(existing))
                    continue
                row = FrontierUrlRow(
                    item_id=item.item_id,
                    site_key=item.site_key,
                    canonical_url=item.canonical_url,
                    url_hash=item.url_hash,
                    priority=item.priority,
                    depth=item.depth,
                    discovered_from=item.discovered_from,
                    status=item.status.value,
                    adapter_version=item.adapter_version,
                    intent_fingerprint=item.intent_fingerprint,
                    dataset_name=item.dataset_name,
                    next_eligible_at=item.next_eligible_at,
                    last_result=item.last_result,
                    region=item.region,
                    request_kwargs_json=_json_dumps(item.request_kwargs),
                )
                session.add(row)
                saved.append(item)
            session.commit()
        return saved

    def list_frontier_items(self, site_key: str | None = None) -> list[FrontierItem]:
        with Session(self._engine) as session:
            statement = select(FrontierUrlRow).order_by(FrontierUrlRow.priority, FrontierUrlRow.created_at)
            if site_key:
                statement = statement.where(FrontierUrlRow.site_key == site_key)
            rows = session.exec(statement).all()
        return [self._to_frontier(row) for row in rows]

    def list_ready_frontier(self, *, limit: int = 100, now: datetime | None = None) -> list[FrontierItem]:
        now = now or utc_now()
        with Session(self._engine) as session:
            statement = (
                select(FrontierUrlRow)
                .where(FrontierUrlRow.status.in_([FrontierStatus.DISCOVERED.value, FrontierStatus.FAILED.value, FrontierStatus.COOLING.value]))
                .where(FrontierUrlRow.next_eligible_at <= now)
                .order_by(FrontierUrlRow.priority, FrontierUrlRow.created_at)
                .limit(limit)
            )
            rows = session.exec(statement).all()
        return [self._to_frontier(row) for row in rows]

    def mark_frontier_status(
        self,
        item_id: str,
        status: FrontierStatus,
        *,
        last_result: str = "",
        cooldown_seconds: int = 0,
    ) -> None:
        with Session(self._engine) as session:
            row = session.get(FrontierUrlRow, item_id)
            if row is None:
                return
            row.status = status.value
            row.last_result = last_result
            row.next_eligible_at = utc_now() + timedelta(seconds=cooldown_seconds)
            row.updated_at = utc_now()
            session.add(row)
            session.commit()

    def upsert_account(self, account: AccountRecord) -> AccountRecord:
        row = AccountRow(
            account_id=account.account_id,
            site_key=account.site_key,
            credential_ref=account.credential_ref,
            status=account.status.value,
            session_state_ref=account.session_state_ref,
            risk_score=account.risk_score,
            last_login_at=account.last_login_at,
            last_refresh_at=account.last_refresh_at,
            warmup_phase=account.warmup_phase,
            owner_policy_json=_json_dumps(account.owner_policy),
            updated_at=utc_now(),
        )
        with Session(self._engine) as session:
            existing = session.get(AccountRow, row.account_id)
            if existing is not None:
                for field in (
                    "site_key",
                    "credential_ref",
                    "status",
                    "session_state_ref",
                    "risk_score",
                    "last_login_at",
                    "last_refresh_at",
                    "warmup_phase",
                    "owner_policy_json",
                    "updated_at",
                ):
                    setattr(existing, field, getattr(row, field))
                session.add(existing)
            else:
                session.add(row)
            session.commit()
        return account

    def get_account(self, account_id: str) -> AccountRecord | None:
        with Session(self._engine) as session:
            row = session.get(AccountRow, account_id)
        return self._to_account(row) if row else None

    def upsert_proxy(self, proxy: ProxyRecord) -> ProxyRecord:
        row = ProxyRow(
            proxy_id=proxy.proxy_id,
            provider=proxy.provider,
            region=proxy.region,
            protocol=proxy.protocol,
            endpoint=proxy.endpoint,
            auth=proxy.auth,
            quality_score=proxy.quality_score,
            ban_score=proxy.ban_score,
            sticky_capable=proxy.sticky_capable,
            supports_browser=proxy.supports_browser,
            status=proxy.status.value,
            updated_at=utc_now(),
        )
        with Session(self._engine) as session:
            existing = session.get(ProxyRow, row.proxy_id)
            if existing is not None:
                for field in (
                    "provider",
                    "region",
                    "protocol",
                    "endpoint",
                    "auth",
                    "quality_score",
                    "ban_score",
                    "sticky_capable",
                    "supports_browser",
                    "status",
                    "updated_at",
                ):
                    setattr(existing, field, getattr(row, field))
                session.add(existing)
            else:
                session.add(row)
            session.commit()
        return proxy

    def get_proxy(self, proxy_id: str) -> ProxyRecord | None:
        with Session(self._engine) as session:
            row = session.get(ProxyRow, proxy_id)
        return self._to_proxy(row) if row else None

    def list_leases(self) -> list[LeaseRecord]:
        with Session(self._engine) as session:
            rows = session.exec(select(LeaseRow).order_by(LeaseRow.acquired_at.desc())).all()
        return [self._to_lease(row) for row in rows]

    def lease_account(
        self,
        *,
        site_key: str,
        job_type: JobType,
        job_id: str,
        region: str = "global",
        account_id: str = "",
        ttl_seconds: int = 900,
    ) -> LeaseRecord | None:
        with Session(self._engine) as session:
            statement = select(AccountRow).where(AccountRow.site_key == site_key).where(
                AccountRow.status.in_([AccountStatus.ACTIVE.value, AccountStatus.WARMING.value])
            )
            if account_id:
                statement = statement.where(AccountRow.account_id == account_id)
            accounts = session.exec(statement).all()
            for account in accounts:
                if self._has_active_lease(session, ResourceType.ACCOUNT, account.account_id):
                    continue
                lease = LeaseRecord(
                    resource_type=ResourceType.ACCOUNT,
                    resource_id=account.account_id,
                    job_type=job_type,
                    job_id=job_id,
                    site_key=site_key,
                    region=region,
                    expires_at=utc_now() + timedelta(seconds=ttl_seconds),
                )
                session.add(
                    LeaseRow(
                        lease_id=lease.lease_id,
                        resource_type=lease.resource_type.value,
                        resource_id=lease.resource_id,
                        job_type=lease.job_type.value,
                        job_id=lease.job_id,
                        site_key=lease.site_key,
                        region=lease.region,
                        status=lease.status.value,
                        acquired_at=lease.acquired_at,
                        expires_at=lease.expires_at,
                        details_json=_json_dumps(lease.details),
                    )
                )
                session.commit()
                return lease
        return None

    def lease_proxy(
        self,
        *,
        job_type: JobType,
        job_id: str,
        site_key: str,
        region: str = "global",
        proxy_id: str = "",
        supports_browser: bool = False,
        sticky_required: bool = False,
        ttl_seconds: int = 900,
    ) -> LeaseRecord | None:
        with Session(self._engine) as session:
            statement = select(ProxyRow).where(ProxyRow.status == ProxyStatus.ACTIVE.value)
            if region:
                statement = statement.where(ProxyRow.region == region)
            if proxy_id:
                statement = statement.where(ProxyRow.proxy_id == proxy_id)
            if supports_browser:
                statement = statement.where(ProxyRow.supports_browser == True)  # noqa: E712
            if sticky_required:
                statement = statement.where(ProxyRow.sticky_capable == True)  # noqa: E712
            proxies = session.exec(statement.order_by(ProxyRow.ban_score, ProxyRow.quality_score.desc())).all()
            for proxy in proxies:
                if self._has_active_lease(session, ResourceType.PROXY, proxy.proxy_id):
                    continue
                lease = LeaseRecord(
                    resource_type=ResourceType.PROXY,
                    resource_id=proxy.proxy_id,
                    job_type=job_type,
                    job_id=job_id,
                    site_key=site_key,
                    region=region,
                    expires_at=utc_now() + timedelta(seconds=ttl_seconds),
                )
                session.add(
                    LeaseRow(
                        lease_id=lease.lease_id,
                        resource_type=lease.resource_type.value,
                        resource_id=lease.resource_id,
                        job_type=lease.job_type.value,
                        job_id=lease.job_id,
                        site_key=lease.site_key,
                        region=lease.region,
                        status=lease.status.value,
                        acquired_at=lease.acquired_at,
                        expires_at=lease.expires_at,
                        details_json=_json_dumps(lease.details),
                    )
                )
                session.commit()
                return lease
        return None

    def release_lease(self, lease_id: str, *, details: dict[str, Any] | None = None) -> None:
        with Session(self._engine) as session:
            row = session.get(LeaseRow, lease_id)
            if row is None:
                return
            row.status = LeaseStatus.RELEASED.value
            row.released_at = utc_now()
            if details:
                row.details_json = _json_dumps(details)
            session.add(row)
            session.commit()

    def upsert_worker_heartbeat(self, heartbeat: WorkerHeartbeat) -> WorkerHeartbeat:
        row = WorkerHeartbeatRow(
            worker_id=heartbeat.worker_id,
            worker_type=heartbeat.worker_type.value,
            region=heartbeat.region,
            queue_name=heartbeat.queue_name,
            status=heartbeat.status,
            details_json=_json_dumps(heartbeat.details),
            last_seen_at=heartbeat.last_seen_at,
        )
        with Session(self._engine) as session:
            existing = session.get(WorkerHeartbeatRow, row.worker_id)
            if existing is not None:
                existing.worker_type = row.worker_type
                existing.region = row.region
                existing.queue_name = row.queue_name
                existing.status = row.status
                existing.details_json = row.details_json
                existing.last_seen_at = row.last_seen_at
                session.add(existing)
            else:
                session.add(row)
            session.commit()
        return heartbeat

    def record_verification(
        self,
        *,
        verification_id: str,
        site_key: str,
        adapter_version: str,
        reverse_job_id: str,
        verified: bool,
        report_ref: str,
        notes: str,
    ) -> None:
        row = VerificationRunRow(
            verification_id=verification_id,
            site_key=site_key,
            adapter_version=adapter_version,
            reverse_job_id=reverse_job_id,
            verified=verified,
            report_ref=report_ref,
            notes=notes,
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()

    def store_result_envelope(self, envelope: ResultEnvelope) -> ResultEnvelope:
        row = ResultEnvelopeRow(
            result_id=envelope.result_id,
            job_id=envelope.job_id,
            site_key=envelope.site_key,
            adapter_version=envelope.adapter_version,
            account_id=envelope.account_id,
            proxy_id=envelope.proxy_id,
            request_fingerprint=envelope.request_fingerprint,
            source_url=envelope.source_url,
            response_status=envelope.response_status,
            schema_version=envelope.schema_version,
            dataset_contract_version=envelope.dataset_contract_version,
            adapter_package_version=envelope.adapter_package_version,
            raw_payload_ref=envelope.raw_payload_ref,
            normalized_payload_json=_json_dumps(envelope.normalized_payload),
            dataset_name=envelope.dataset_name,
            extractor_version=envelope.extractor_version,
            observed_at=envelope.observed_at,
            stored_at=utc_now(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
        return envelope

    def list_results(self) -> list[ResultEnvelope]:
        with Session(self._engine) as session:
            rows = session.exec(select(ResultEnvelopeRow).order_by(ResultEnvelopeRow.observed_at.desc())).all()
        return [
            ResultEnvelope(
                result_id=row.result_id,
                job_id=row.job_id,
                site_key=row.site_key,
                adapter_version=row.adapter_version,
                account_id=row.account_id,
                proxy_id=row.proxy_id,
                request_fingerprint=row.request_fingerprint,
                source_url=row.source_url,
                response_status=row.response_status,
                schema_version=row.schema_version,
                dataset_contract_version=row.dataset_contract_version,
                adapter_package_version=row.adapter_package_version,
                raw_payload_ref=row.raw_payload_ref,
                normalized_payload=_json_loads(row.normalized_payload_json, None),
                dataset_name=row.dataset_name,
                extractor_version=row.extractor_version,
                observed_at=row.observed_at,
            )
            for row in rows
        ]

    def upsert_dataset_schema(self, schema: DatasetSchema) -> DatasetSchema:
        schema_id = f"{schema.dataset_name}:{schema.version}"
        row = DatasetSchemaRow(
            schema_id=schema_id,
            dataset_name=schema.dataset_name,
            version=schema.version,
            schema_definition_json=_json_dumps(schema.schema_definition),
            extractor_version=schema.extractor_version,
            created_at=schema.created_at,
        )
        with Session(self._engine) as session:
            existing = session.get(DatasetSchemaRow, schema_id)
            if existing is not None:
                existing.schema_definition_json = row.schema_definition_json
                existing.extractor_version = row.extractor_version
                session.add(existing)
            else:
                session.add(row)
            session.commit()
        return schema

    def _has_active_lease(self, session: Session, resource_type: ResourceType, resource_id: str) -> bool:
        now = utc_now()
        statement = (
            select(LeaseRow)
            .where(LeaseRow.resource_type == resource_type.value)
            .where(LeaseRow.resource_id == resource_id)
            .where(LeaseRow.status == LeaseStatus.ACTIVE.value)
            .where(LeaseRow.expires_at > now)
        )
        return session.exec(statement).first() is not None

    def _update_job(
        self,
        job_type: JobType,
        job_id: str,
        status: JobStatus,
        *,
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        row_cls = _JOB_ROWS[job_type]
        with Session(self._engine) as session:
            row = session.get(row_cls, job_id)
            if row is None:
                return
            row.status = status.value
            row.error = error
            row.result_json = _json_dumps(result or {})
            row.updated_at = utc_now()
            if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.DELEGATED, JobStatus.CANCELLED}:
                row.completed_at = utc_now()
            session.add(row)
            session.commit()

    def _to_job(self, job_type: JobType, row: JobRowBase) -> QueuedJob:
        spec_cls = _JOB_SPECS[job_type]
        payload = _json_loads(row.payload_json, {})
        spec = spec_cls.model_validate(payload)
        parent_job_id = ""
        if isinstance(row, CrawlJobRow):
            parent_job_id = row.parent_job_id
        elif isinstance(row, BridgeJobRow):
            parent_job_id = row.parent_crawl_job_id
        return QueuedJob(
            job_type=job_type,
            job_id=row.job_id,
            site_key=row.site_key,
            queue=row.queue,
            region=row.region,
            priority=row.priority,
            status=JobStatus(row.status),
            spec=spec,
            parent_job_id=parent_job_id,
            created_at=row.created_at,
        )

    def _to_adapter(self, row: AdapterVersionRow) -> AdapterVersion:
        return AdapterVersion(
            site_key=row.site_key,
            version=row.version,
            output_mode=row.output_mode,
            adapter_package_version=row.adapter_package_version,
            dataset_contract_version=row.dataset_contract_version,
            intent_fingerprint=row.intent_fingerprint,
            request_contract_hash=row.request_contract_hash,
            family_id=row.family_id,
            crawler_script_ref=row.crawler_script_ref,
            bridge_server_ref=row.bridge_server_ref,
            manifest_ref=row.manifest_ref,
            adapter_package_ref=row.adapter_package_ref,
            request_contract=_json_loads(row.request_contract_json, None),
            dataset_contract=_json_loads(row.dataset_contract_json, None),
            capability_profile=_json_loads(row.capability_profile_json, None),
            verification_profile=_json_loads(row.verification_profile_json, None),
            signature_spec=_json_loads(row.signature_spec_json, None),
            verification_report_ref=row.verification_report_ref,
            compatibility_tags=_json_loads(row.compatibility_tags_json, []),
            source_reverse_job_id=row.source_reverse_job_id,
            created_at=row.created_at,
            verified_at=row.verified_at,
        )

    def _to_frontier(self, row: FrontierUrlRow) -> FrontierItem:
        return FrontierItem(
            item_id=row.item_id,
            site_key=row.site_key,
            canonical_url=row.canonical_url,
            url_hash=row.url_hash,
            priority=row.priority,
            depth=row.depth,
            discovered_from=row.discovered_from,
            status=FrontierStatus(row.status),
            adapter_version=row.adapter_version,
            intent_fingerprint=row.intent_fingerprint,
            dataset_name=row.dataset_name,
            next_eligible_at=row.next_eligible_at,
            last_result=row.last_result,
            region=row.region,
            request_kwargs=_json_loads(row.request_kwargs_json, {}),
        )

    def _to_account(self, row: AccountRow) -> AccountRecord:
        return AccountRecord(
            account_id=row.account_id,
            site_key=row.site_key,
            credential_ref=row.credential_ref,
            status=AccountStatus(row.status),
            session_state_ref=row.session_state_ref,
            risk_score=row.risk_score,
            last_login_at=row.last_login_at,
            last_refresh_at=row.last_refresh_at,
            warmup_phase=row.warmup_phase,
            owner_policy=_json_loads(row.owner_policy_json, {}),
        )

    def _to_proxy(self, row: ProxyRow) -> ProxyRecord:
        return ProxyRecord(
            proxy_id=row.proxy_id,
            provider=row.provider,
            region=row.region,
            protocol=row.protocol,
            endpoint=row.endpoint,
            auth=row.auth,
            quality_score=row.quality_score,
            ban_score=row.ban_score,
            sticky_capable=row.sticky_capable,
            supports_browser=row.supports_browser,
            status=ProxyStatus(row.status),
        )

    def _to_lease(self, row: LeaseRow) -> LeaseRecord:
        return LeaseRecord(
            lease_id=row.lease_id,
            resource_type=ResourceType(row.resource_type),
            resource_id=row.resource_id,
            job_type=JobType(row.job_type),
            job_id=row.job_id,
            site_key=row.site_key,
            region=row.region,
            status=LeaseStatus(row.status),
            acquired_at=row.acquired_at,
            expires_at=row.expires_at,
            released_at=row.released_at,
            details=_json_loads(row.details_json, {}),
        )


class FileEventBus:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def publish(self, topic: str, payload: dict[str, Any], *, key: str = "") -> Path:
        path = self._root / f"{topic}.jsonl"
        event = {
            "topic": topic,
            "key": key,
            "payload": payload,
            "published_at": utc_now().isoformat(),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json_dumps(event) + "\n")
        return path


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put_json(self, key: str, payload: Any) -> str:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dumps(payload), encoding="utf-8")
        return str(path.resolve())

    def put_file(self, key: str, source: Path) -> str:
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
        return str(path.resolve())

    def resolve(self, ref: str) -> Path:
        return Path(ref)


class LocalWarehouseSink:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def write_record(self, layer: str, dataset_name: str, payload: dict[str, Any]) -> str:
        path = self._root / layer / f"{dataset_name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json_dumps(payload) + "\n")
        return str(path.resolve())
