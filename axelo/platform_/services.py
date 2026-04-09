from __future__ import annotations

from typing import Any

from axelo.models.contracts import CaptureIntent
from axelo.platform.models import (
    AccountRecord,
    BridgeJobSpec,
    CrawlJobSpec,
    FrontierItem,
    FrontierSeedRequest,
    FrontierStatus,
    JobType,
    ProxyRecord,
    ResourceType,
    ResultEnvelope,
    ReverseJobSpec,
    SessionRefreshJobSpec,
    canonicalize_url,
    frontier_hash,
    site_key_from_url,
    utc_now,
)
from axelo.platform.storage import FileEventBus, LocalObjectStore, LocalWarehouseSink, PlatformStore
from axelo.platform.topics import (
    TOPIC_FRONTIER_DISCOVERED,
    TOPIC_JOBS_BRIDGE,
    TOPIC_JOBS_CRAWL,
    TOPIC_JOBS_REVERSE,
    TOPIC_JOBS_SESSION_REFRESH,
    TOPIC_PLATFORM_EVENTS,
    TOPIC_RESOURCE_EVENTS,
    TOPIC_RESULTS_NORMALIZED,
    TOPIC_RESULTS_RAW,
)


class ControlPlaneService:
    def __init__(self, store: PlatformStore, event_bus: FileEventBus) -> None:
        self._store = store
        self._bus = event_bus

    def submit_reverse_job(self, spec: ReverseJobSpec):
        job = self._store.submit_job(JobType.REVERSE, spec)
        self._bus.publish(TOPIC_JOBS_REVERSE, {"job_id": job.job_id, "site_key": job.site_key}, key=job.site_key)
        return job

    def submit_crawl_job(self, spec: CrawlJobSpec):
        if not spec.adapter_version:
            adapter = self._store.latest_adapter(spec.site_key)
            if adapter is not None:
                spec.adapter_version = adapter.version
                if spec.dataset_name == "default" and adapter.dataset_contract:
                    spec.dataset_name = str(adapter.dataset_contract.get("dataset_name") or spec.dataset_name)
                if not spec.intent_fingerprint and adapter.intent_fingerprint:
                    spec.intent_fingerprint = adapter.intent_fingerprint
        job = self._store.submit_job(JobType.CRAWL, spec)
        self._bus.publish(TOPIC_JOBS_CRAWL, {"job_id": job.job_id, "site_key": job.site_key}, key=job.site_key)
        return job

    def submit_bridge_job(self, spec: BridgeJobSpec):
        job = self._store.submit_job(JobType.BRIDGE, spec)
        self._bus.publish(TOPIC_JOBS_BRIDGE, {"job_id": job.job_id, "site_key": job.site_key}, key=job.site_key)
        return job

    def submit_session_refresh_job(self, spec: SessionRefreshJobSpec):
        job = self._store.submit_job(JobType.SESSION_REFRESH, spec)
        self._bus.publish(TOPIC_JOBS_SESSION_REFRESH, {"job_id": job.job_id, "site_key": job.site_key}, key=job.site_key)
        return job

    def list_adapters(self, site_key: str):
        return self._store.list_adapters(site_key)


class FrontierService:
    def __init__(self, store: PlatformStore, event_bus: FileEventBus) -> None:
        self._store = store
        self._bus = event_bus

    def seed(self, request: FrontierSeedRequest) -> list[FrontierItem]:
        items: list[FrontierItem] = []
        for url in request.urls:
            canonical_url = canonicalize_url(url)
            site_key = request.site_key or site_key_from_url(canonical_url)
            intent_fingerprint = request.intent_fingerprint
            dataset_name = request.dataset_name
            if request.intent:
                intent = CaptureIntent.model_validate(request.intent)
                intent_fingerprint = intent_fingerprint or intent.fingerprint
                dataset_name = dataset_name or intent.dataset_name
            items.append(
                FrontierItem(
                    site_key=site_key,
                    canonical_url=canonical_url,
                    url_hash=frontier_hash(site_key, canonical_url),
                    priority=request.priority,
                    depth=request.depth,
                    discovered_from=request.discovered_from,
                    adapter_version=request.adapter_version,
                    intent_fingerprint=intent_fingerprint,
                    dataset_name=dataset_name,
                    region=request.region,
                    request_kwargs=dict(request.request_kwargs),
                )
            )
        saved = self._store.submit_frontier_items(items)
        for item in saved:
            self._bus.publish(TOPIC_FRONTIER_DISCOVERED, item.model_dump(mode="json"), key=item.site_key)
        return saved


class ResourceManager:
    def __init__(self, store: PlatformStore, event_bus: FileEventBus) -> None:
        self._store = store
        self._bus = event_bus

    def upsert_account(self, account: AccountRecord) -> AccountRecord:
        saved = self._store.upsert_account(account)
        self._bus.publish(TOPIC_RESOURCE_EVENTS, {"resource": ResourceType.ACCOUNT.value, "account_id": saved.account_id}, key=saved.site_key)
        return saved

    def upsert_proxy(self, proxy: ProxyRecord) -> ProxyRecord:
        saved = self._store.upsert_proxy(proxy)
        self._bus.publish(TOPIC_RESOURCE_EVENTS, {"resource": ResourceType.PROXY.value, "proxy_id": saved.proxy_id}, key=saved.region)
        return saved

    def lease_account(self, *, site_key: str, job_type: JobType, job_id: str, region: str = "global", account_id: str = ""):
        lease = self._store.lease_account(site_key=site_key, job_type=job_type, job_id=job_id, region=region, account_id=account_id)
        if lease:
            self._bus.publish(TOPIC_RESOURCE_EVENTS, {"event": "lease_account", "lease_id": lease.lease_id, "resource_id": lease.resource_id}, key=site_key)
        return lease

    def lease_proxy(
        self,
        *,
        site_key: str,
        job_type: JobType,
        job_id: str,
        region: str = "global",
        proxy_id: str = "",
        requires_browser: bool = False,
        sticky_required: bool = False,
    ):
        lease = self._store.lease_proxy(
            site_key=site_key,
            job_type=job_type,
            job_id=job_id,
            region=region,
            proxy_id=proxy_id,
            supports_browser=requires_browser,
            sticky_required=sticky_required,
        )
        if lease:
            self._bus.publish(TOPIC_RESOURCE_EVENTS, {"event": "lease_proxy", "lease_id": lease.lease_id, "resource_id": lease.resource_id}, key=region)
        return lease

    def release_lease(self, lease_id: str, *, details: dict[str, Any] | None = None) -> None:
        self._store.release_lease(lease_id, details=details)


class IngestService:
    def __init__(
        self,
        store: PlatformStore,
        event_bus: FileEventBus,
        object_store: LocalObjectStore,
        warehouse: LocalWarehouseSink,
    ) -> None:
        self._store = store
        self._bus = event_bus
        self._object_store = object_store
        self._warehouse = warehouse

    def ingest(self, envelope: ResultEnvelope, *, raw_payload: Any) -> ResultEnvelope:
        if not envelope.raw_payload_ref:
            envelope.raw_payload_ref = self._object_store.put_json(
                f"bronze/results/{envelope.job_id}.json",
                raw_payload,
            )
        self._store.store_result_envelope(envelope)
        self._warehouse.write_record("silver", envelope.dataset_name, envelope.model_dump(mode="json"))
        self._bus.publish(TOPIC_RESULTS_RAW, {"job_id": envelope.job_id, "raw_payload_ref": envelope.raw_payload_ref}, key=envelope.site_key)
        self._bus.publish(TOPIC_RESULTS_NORMALIZED, envelope.model_dump(mode="json"), key=envelope.site_key)
        return envelope


class SchedulerService:
    def __init__(self, store: PlatformStore, control: ControlPlaneService) -> None:
        self._store = store
        self._control = control

    def dispatch_frontier(self, *, limit: int = 100) -> list[str]:
        created_job_ids: list[str] = []
        for item in self._store.list_ready_frontier(limit=limit):
            adapter = self._store.get_adapter(item.site_key, item.adapter_version) if item.adapter_version else self._store.latest_adapter(item.site_key)
            if adapter is None:
                if not self._store.open_job_exists(JobType.REVERSE, item.site_key):
                    reverse_job = self._control.submit_reverse_job(
                        ReverseJobSpec(
                            url=item.canonical_url,
                            site_key=item.site_key,
                            goal="分析并复现请求签名/Token 生成逻辑",
                            intent_fingerprint=item.intent_fingerprint,
                            dataset_name=item.dataset_name or "default",
                            metadata={"frontier_item_id": item.item_id},
                        )
                    )
                    created_job_ids.append(reverse_job.job_id)
                self._store.mark_frontier_status(
                    item.item_id,
                    FrontierStatus.COOLING,
                    last_result="adapter_missing",
                    cooldown_seconds=300,
                )
                continue

            crawl_job = self._control.submit_crawl_job(
                CrawlJobSpec(
                    site_key=item.site_key,
                    site_url=item.canonical_url,
                    source_url=item.canonical_url,
                    adapter_version=adapter.version,
                    frontier_item_id=item.item_id,
                    action=str(item.request_kwargs.get("action", "page")),
                    crawl_kwargs=dict(item.request_kwargs),
                    intent_fingerprint=item.intent_fingerprint,
                    dataset_name=item.dataset_name or "default",
                    schema_version=adapter.dataset_contract_version or "v1",
                    region=item.region,
                    priority=item.priority,
                )
            )
            created_job_ids.append(crawl_job.job_id)
            self._store.mark_frontier_status(item.item_id, FrontierStatus.QUEUED, last_result=f"crawl_job={crawl_job.job_id}")
        return created_job_ids

    def emit_platform_event(self, payload: dict[str, Any], event_bus: FileEventBus) -> None:
        payload = dict(payload)
        payload["emitted_at"] = utc_now().isoformat()
        event_bus.publish(TOPIC_PLATFORM_EVENTS, payload)
