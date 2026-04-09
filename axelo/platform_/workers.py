from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from axelo.browser.driver import BrowserDriver
from axelo.browser.profiles import PROFILES
from axelo.browser.state_store import BrowserStateStore
from axelo.config import settings
from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.models.contracts import AdapterPackage
from axelo.models.session_state import SessionState
from axelo.models.target import TargetSite
# Lazy import MasterOrchestrator - may not be available
def _get_orchestrator_class():
    try:
        from axelo.orchestrator.master import MasterOrchestrator
        return MasterOrchestrator
    except ImportError:
        return None
from axelo.platform.models import (
    AccountStatus,
    AdapterVersion,
    BridgeJobSpec,
    CrawlJobSpec,
    JobType,
    ResultEnvelope,
    ReverseJobSpec,
    SessionRefreshJobSpec,
    WorkerHeartbeat,
    WorkerType,
    utc_now,
)
from axelo.platform.runtime import PlatformRuntime
from axelo.platform.topics import TOPIC_PLATFORM_EVENTS
from axelo.storage.session_state_store import SessionStateStore
from axelo.verification.replayer import RequestReplayer


def build_adapter_version(
    *,
    site_key: str,
    reverse_job_id: str,
    generated: GeneratedCode,
    analysis: AnalysisResult | None,
    report_ref: str,
    verified: bool,
) -> AdapterVersion:
    package = _load_adapter_package(generated.adapter_package_path)
    material = "|".join(
        [
            site_key,
            reverse_job_id,
            str(generated.crawler_script_path or ""),
            str(generated.manifest_path or ""),
            str(report_ref),
        ]
    )
    version = hashlib.sha1(material.encode("utf-8")).hexdigest()[:12]
    compatibility_tags = [generated.output_mode]
    compatibility_tags.append("verified" if verified else "unverified")
    return AdapterVersion(
        site_key=site_key,
        version=version,
        output_mode=generated.output_mode,
        adapter_package_version=package.package_version if package else "v1",
        dataset_contract_version=package.dataset_contract.schema_version if package else "v1",
        intent_fingerprint=package.intent_fingerprint if package else "",
        request_contract_hash=package.request_contract_hash if package else "",
        family_id=package.family_id if package else (analysis.signature_family if analysis else "unknown"),
        crawler_script_ref=str(generated.crawler_script_path) if generated.crawler_script_path else "",
        bridge_server_ref=str(generated.bridge_server_path) if generated.bridge_server_path else "",
        manifest_ref=str(generated.manifest_path) if generated.manifest_path else "",
        adapter_package_ref=str(generated.adapter_package_path) if generated.adapter_package_path else "",
        request_contract=package.request_contract.model_dump(mode="json") if package else None,
        dataset_contract=package.dataset_contract.model_dump(mode="json") if package else None,
        capability_profile=package.capability_profile.model_dump(mode="json") if package else None,
        verification_profile=package.verification_profile.model_dump(mode="json") if package else None,
        signature_spec=analysis.signature_spec.model_dump(mode="json") if analysis and analysis.signature_spec else None,
        verification_report_ref=report_ref,
        compatibility_tags=list(dict.fromkeys((package.compatibility_tags if package else []) + compatibility_tags)),
        source_reverse_job_id=reverse_job_id,
        verified_at=utc_now() if verified else None,
    )


class WorkerBase:
    def __init__(
        self,
        runtime: PlatformRuntime,
        *,
        worker_type: WorkerType,
        queue_name: str = "default",
        region: str = "global",
        worker_id: str | None = None,
    ) -> None:
        self._runtime = runtime
        self._type = worker_type
        self._queue_name = queue_name
        self._region = region
        self._worker_id = worker_id or f"{worker_type.value}-{utc_now().strftime('%H%M%S%f')[:10]}"

    def _heartbeat(self, status: str, *, details: dict[str, Any] | None = None) -> None:
        self._runtime.store.upsert_worker_heartbeat(
            WorkerHeartbeat(
                worker_id=self._worker_id,
                worker_type=self._type,
                region=self._region,
                queue_name=self._queue_name,
                status=status,
                details=details or {},
            )
        )

    async def run_forever(self, *, poll_interval: float = 1.0, limit: int | None = None) -> int:
        processed = 0
        while limit is None or processed < limit:
            did_work = await self.run_once()
            if did_work:
                processed += 1
                continue
            await asyncio.sleep(poll_interval)
        return processed

    async def run_once(self) -> bool:
        raise NotImplementedError


class ReverseWorker(WorkerBase):
    def __init__(
        self,
        runtime: PlatformRuntime,
        *,
        queue_name: str = "default",
        region: str = "global",
    ) -> None:
        super().__init__(runtime, worker_type=WorkerType.REVERSE, queue_name=queue_name, region=region)
        self._orchestrator_class = _get_orchestrator_class()

    async def run_once(self) -> bool:
        # Check if orchestrator is available
        if self._orchestrator_class is None:
            log.error("orchestrator_not_available", message="MasterOrchestrator is not available. Please ensure the orchestrator module is installed.")
            self._heartbeat("error", details={"error": "orchestrator not available"})
            return False

    async def run_once(self) -> bool:
        job = self._runtime.store.acquire_job(JobType.REVERSE, queue=self._queue_name, region=self._region)
        if job is None:
            self._heartbeat("idle")
            return False
        self._heartbeat("running", details={"job_id": job.job_id})
        spec = ReverseJobSpec.model_validate(job.spec.model_dump(mode="json"))
        browser_profile = PROFILES.get(spec.browser_profile_name, PROFILES["default"]).model_copy(deep=True)
        
        # Use orchestrator class to create instance
        orchestrator = self._orchestrator_class()
        result = await orchestrator.run(
            url=spec.url,
            goal=spec.goal,
            target_hint=spec.target_hint,
            use_case=spec.use_case,
            authorization_status=spec.authorization_status,
            replay_mode=spec.replay_mode,
            mode_name="auto",
            session_id=job.job_id,
            budget_usd=spec.budget_usd,
            known_endpoint=spec.known_endpoint,
            antibot_type=spec.antibot_type,
            requires_login=spec.requires_login,
            output_format=spec.output_format,
            crawl_rate=spec.crawl_rate,
            intent=spec.intent,
            browser_profile=browser_profile,
        )
        if not result.completed or result.generated is None:
            self._runtime.store.fail_job(JobType.REVERSE, job.job_id, result.error or "reverse run failed")
            self._runtime.event_bus.publish(TOPIC_PLATFORM_EVENTS, {"event": "reverse_failed", "job_id": job.job_id, "error": result.error or ""}, key=spec.site_key)
            return True

        report_ref = ""
        if result.report_path and result.report_path.exists():
            report_ref = self._runtime.object_store.put_file(
                f"reports/{spec.site_key}/{job.job_id}/run_report.json",
                result.report_path,
            )
        if result.generated.crawler_script_path and result.generated.crawler_script_path.exists():
            result.generated.crawler_script_path = Path(
                self._runtime.object_store.put_file(
                    f"adapters/{spec.site_key}/{job.job_id}/crawler.py",
                    result.generated.crawler_script_path,
                )
            )
        if result.generated.bridge_server_path and result.generated.bridge_server_path.exists():
            result.generated.bridge_server_path = Path(
                self._runtime.object_store.put_file(
                    f"adapters/{spec.site_key}/{job.job_id}/bridge_server.js",
                    result.generated.bridge_server_path,
                )
            )
        if result.generated.manifest_path and result.generated.manifest_path.exists():
            result.generated.manifest_path = Path(
                self._runtime.object_store.put_file(
                    f"adapters/{spec.site_key}/{job.job_id}/crawler_manifest.json",
                    result.generated.manifest_path,
                )
            )
        if result.generated.adapter_package_path and result.generated.adapter_package_path.exists():
            result.generated.adapter_package_path = Path(
                self._runtime.object_store.put_file(
                    f"adapters/{spec.site_key}/{job.job_id}/adapter_package.json",
                    result.generated.adapter_package_path,
                )
            )
        adapter = build_adapter_version(
            site_key=spec.site_key,
            reverse_job_id=job.job_id,
            generated=result.generated,
            analysis=result.analysis,
            report_ref=report_ref,
            verified=result.verified,
        )
        self._runtime.store.register_adapter_version(adapter)
        self._runtime.store.record_verification(
            verification_id=f"verify-{job.job_id}",
            site_key=spec.site_key,
            adapter_version=adapter.version,
            reverse_job_id=job.job_id,
            verified=result.verified,
            report_ref=report_ref,
            notes=result.generated.verification_notes if result.generated else "",
        )
        self._runtime.store.complete_job(
            JobType.REVERSE,
            job.job_id,
            {
                "adapter_version": adapter.version,
                "verified": result.verified,
                "report_ref": report_ref,
            },
        )
        self._runtime.event_bus.publish(TOPIC_PLATFORM_EVENTS, {"event": "reverse_completed", "job_id": job.job_id, "adapter_version": adapter.version}, key=spec.site_key)
        return True


class CrawlWorker(WorkerBase):
    def __init__(self, runtime: PlatformRuntime, *, worker_type: WorkerType = WorkerType.CRAWL, queue_name: str = "default", region: str = "global") -> None:
        super().__init__(runtime, worker_type=worker_type, queue_name=queue_name, region=region)
        self._replayer = RequestReplayer()

    async def run_once(self) -> bool:
        job_type = JobType.BRIDGE if self._type == WorkerType.BRIDGE else JobType.CRAWL
        job = self._runtime.store.acquire_job(job_type, queue=self._queue_name, region=self._region)
        if job is None:
            self._heartbeat("idle")
            return False
        self._heartbeat("running", details={"job_id": job.job_id})
        spec = job.spec
        if job_type == JobType.BRIDGE:
            spec = BridgeJobSpec.model_validate(spec.model_dump(mode="json"))
        else:
            spec = CrawlJobSpec.model_validate(spec.model_dump(mode="json"))
        adapter = self._runtime.store.get_adapter(spec.site_key, spec.adapter_version) if spec.adapter_version else self._runtime.store.latest_adapter(spec.site_key)
        if adapter is None:
            self._runtime.store.fail_job(job_type, job.job_id, "adapter version not found")
            return True

        account_lease = self._runtime.resources.lease_account(site_key=spec.site_key, job_type=job_type, job_id=job.job_id, region=spec.region, account_id=spec.account_id)
        adapter_needs_bridge = adapter.output_mode == "bridge" or bool((adapter.capability_profile or {}).get("needs_bridge"))
        proxy_lease = self._runtime.resources.lease_proxy(
            site_key=spec.site_key,
            job_type=job_type,
            job_id=job.job_id,
            region=spec.region,
            proxy_id=spec.proxy_id,
            requires_browser=adapter_needs_bridge,
            sticky_required=adapter_needs_bridge,
        )
        try:
            if job_type == JobType.CRAWL and adapter_needs_bridge:
                bridge_job = self._runtime.control.submit_bridge_job(
                    BridgeJobSpec(
                        site_key=spec.site_key,
                        site_url=spec.site_url,
                        source_url=spec.source_url,
                        adapter_version=adapter.version,
                        frontier_item_id=spec.frontier_item_id,
                        action=spec.action,
                        crawl_kwargs=dict(spec.crawl_kwargs),
                        output_format=spec.output_format,
                        dataset_name=spec.dataset_name,
                        schema_version=spec.schema_version,
                        intent=spec.intent,
                        intent_fingerprint=spec.intent_fingerprint,
                        account_id=spec.account_id,
                        proxy_id=spec.proxy_id,
                        extractor_version=spec.extractor_version,
                        parent_crawl_job_id=job.job_id,
                        region=spec.region,
                        priority=spec.priority,
                    )
                )
                self._runtime.store.delegate_job(JobType.CRAWL, job.job_id, bridge_job.job_id)
                return True

            await self._execute_and_ingest(job.job_id, spec, adapter, account_lease.resource_id if account_lease else "", proxy_lease.resource_id if proxy_lease else "")
            self._runtime.store.complete_job(job_type, job.job_id, {"adapter_version": adapter.version})
            if isinstance(spec, BridgeJobSpec) and spec.parent_crawl_job_id:
                self._runtime.store.complete_job(JobType.CRAWL, spec.parent_crawl_job_id, {"bridge_job_id": job.job_id, "adapter_version": adapter.version})
            return True
        except Exception as exc:
            self._runtime.store.fail_job(job_type, job.job_id, str(exc))
            if isinstance(spec, BridgeJobSpec) and spec.parent_crawl_job_id:
                self._runtime.store.fail_job(JobType.CRAWL, spec.parent_crawl_job_id, f"bridge failed: {exc}")
            return True
        finally:
            if account_lease:
                self._runtime.resources.release_lease(account_lease.lease_id, details={"job_id": job.job_id})
            if proxy_lease:
                self._runtime.resources.release_lease(proxy_lease.lease_id, details={"job_id": job.job_id})

    async def _execute_and_ingest(
        self,
        job_id: str,
        spec: CrawlJobSpec,
        adapter: AdapterVersion,
        account_id: str,
        proxy_id: str,
    ) -> ResultEnvelope:
        output_dir = self._runtime.workspace / "platform" / "job_output" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        init_kwargs, extra_env = self._build_runtime_inputs(account_id=account_id, proxy_id=proxy_id)
        target = TargetSite(url=spec.site_url, session_id=job_id, interaction_goal="platform crawl", output_format=spec.output_format)
        execution = await self._replayer.execute_crawl_subprocess(
            Path(adapter.crawler_script_ref),
            target,
            crawl_kwargs=self._build_crawl_kwargs(spec),
            init_kwargs=init_kwargs,
            output_dir=output_dir,
            extra_env=extra_env,
        )
        if execution.error:
            raise RuntimeError(execution.error)
        envelope = ResultEnvelope(
            job_id=job_id,
            site_key=spec.site_key,
            adapter_version=adapter.version,
            account_id=account_id,
            proxy_id=proxy_id,
            request_fingerprint=self._fingerprint(spec),
            source_url=spec.source_url,
            response_status=200,
            schema_version=spec.schema_version,
            dataset_contract_version=adapter.dataset_contract_version,
            adapter_package_version=adapter.adapter_package_version,
            normalized_payload=execution.crawl_data,
            dataset_name=spec.dataset_name or ((adapter.dataset_contract or {}).get("dataset_name") if adapter.dataset_contract else "default"),
            extractor_version=spec.extractor_version,
        )
        return self._runtime.ingest.ingest(envelope, raw_payload={"headers": execution.headers, "data": execution.crawl_data})

    def _fingerprint(self, spec: CrawlJobSpec) -> str:
        payload = json.dumps({"url": spec.source_url, "action": spec.action, "kwargs": spec.crawl_kwargs}, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    def _build_crawl_kwargs(self, spec: CrawlJobSpec) -> dict[str, Any]:
        kwargs = dict(spec.crawl_kwargs)
        kwargs.setdefault("action", spec.action)
        if spec.source_url:
            kwargs.setdefault("url", spec.source_url)
        return kwargs

    def _build_runtime_inputs(self, *, account_id: str, proxy_id: str) -> tuple[dict[str, Any], dict[str, str]]:
        init_kwargs: dict[str, Any] = {}
        extra_env: dict[str, str] = {}
        if account_id:
            account = self._runtime.store.get_account(account_id)
            if account and account.session_state_ref and Path(account.session_state_ref).exists():
                session_state = SessionState.model_validate_json(Path(account.session_state_ref).read_text(encoding="utf-8"))
                if session_state.storage_state_path:
                    init_kwargs["storage_state_path"] = session_state.storage_state_path
                if session_state.cookies:
                    init_kwargs["cookies"] = {
                        str(item.get("name")): str(item.get("value"))
                        for item in session_state.cookies
                        if item.get("name") is not None and item.get("value") is not None
                    }
        if proxy_id:
            proxy = self._runtime.store.get_proxy(proxy_id)
            if proxy and proxy.endpoint:
                proxy_url = proxy.endpoint
                if proxy.auth and "://" in proxy_url and "@" not in proxy_url:
                    scheme, remainder = proxy_url.split("://", 1)
                    proxy_url = f"{scheme}://{proxy.auth}@{remainder}"
                extra_env["HTTP_PROXY"] = proxy_url
                extra_env["HTTPS_PROXY"] = proxy_url
        return init_kwargs, extra_env


class BridgeWorker(CrawlWorker):
    def __init__(self, runtime: PlatformRuntime, *, queue_name: str = "default", region: str = "global") -> None:
        super().__init__(runtime, worker_type=WorkerType.BRIDGE, queue_name=queue_name, region=region)


class SessionRefreshWorker(WorkerBase):
    def __init__(self, runtime: PlatformRuntime, *, queue_name: str = "default", region: str = "global") -> None:
        super().__init__(runtime, worker_type=WorkerType.SESSION_REFRESH, queue_name=queue_name, region=region)

    async def run_once(self) -> bool:
        job = self._runtime.store.acquire_job(JobType.SESSION_REFRESH, queue=self._queue_name, region=self._region)
        if job is None:
            self._heartbeat("idle")
            return False
        self._heartbeat("running", details={"job_id": job.job_id})
        spec = SessionRefreshJobSpec.model_validate(job.spec.model_dump(mode="json"))
        account = self._runtime.store.get_account(spec.account_id)
        if account is None:
            self._runtime.store.fail_job(JobType.SESSION_REFRESH, job.job_id, "account not found")
            return True

        profile = PROFILES.get(spec.browser_profile_name, PROFILES["default"]).model_copy(deep=True)
        session_state = SessionState()
        if account.session_state_ref and Path(account.session_state_ref).exists():
            session_state = SessionState.model_validate_json(Path(account.session_state_ref).read_text(encoding="utf-8"))

        store = SessionStateStore(settings.sessions_dir)
        browser_state_store = BrowserStateStore(store)
        try:
            async with BrowserDriver(settings.browser, settings.headless) as driver:
                page = await driver.launch(profile, session_state=session_state)
                await page.goto(spec.refresh_url, wait_until="networkidle")
                await browser_state_store.persist_context(job.job_id, spec.refresh_url, driver.context, session_state)
            account.session_state_ref = str(store.state_path(job.job_id))
            account.last_refresh_at = utc_now()
            account.status = AccountStatus.ACTIVE
            self._runtime.resources.upsert_account(account)
            self._runtime.store.complete_job(JobType.SESSION_REFRESH, job.job_id, {"session_state_ref": account.session_state_ref})
            return True
        except Exception as exc:
            account.status = AccountStatus.CHALLENGED
            self._runtime.resources.upsert_account(account)
            self._runtime.store.fail_job(JobType.SESSION_REFRESH, job.job_id, str(exc))
            return True


def _load_adapter_package(path: Path | None) -> AdapterPackage | None:
    if path is None or not path.exists():
        return None
    try:
        return AdapterPackage.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def worker_from_type(runtime: PlatformRuntime, worker_type: str, *, queue_name: str = "default", region: str = "global") -> WorkerBase:
    mapping: dict[str, type[WorkerBase]] = {
        WorkerType.REVERSE.value: ReverseWorker,
        WorkerType.CRAWL.value: CrawlWorker,
        WorkerType.BRIDGE.value: BridgeWorker,
        WorkerType.SESSION_REFRESH.value: SessionRefreshWorker,
    }
    if worker_type not in mapping:
        raise ValueError(f"Unknown worker type: {worker_type}")
    return mapping[worker_type](runtime, queue_name=queue_name, region=region)
