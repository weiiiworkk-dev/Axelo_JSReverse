from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.orchestrator.runtime import MasterResult
from axelo.platform.models import (
    AccountRecord,
    AdapterVersion,
    CrawlJobSpec,
    FrontierSeedRequest,
    JobType,
    ProxyRecord,
    ProxyStatus,
    ReverseJobSpec,
    SessionRefreshJobSpec,
)
from axelo.platform.runtime import PlatformRuntime
from axelo.platform.workers import CrawlWorker, ReverseWorker, SessionRefreshWorker


def _write_demo_crawler(path: Path, *, bridge: bool = False) -> None:
    body = [
        "class DemoCrawler:",
        "    def __init__(self, **kwargs):",
        "        self.kwargs = kwargs",
        "    def crawl(self, **kwargs):",
        "        return {'url': kwargs.get('url'), 'action': kwargs.get('action'), 'bridge': %s}" % ("True" if bridge else "False"),
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def test_frontier_seed_deduplicates_and_scheduler_dispatches(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    script = tmp_path / "crawler.py"
    manifest = tmp_path / "crawler_manifest.json"
    _write_demo_crawler(script)
    manifest.write_text("{}", encoding="utf-8")
    runtime.store.register_adapter_version(
        AdapterVersion(
            site_key="example.com",
            version="v1",
            output_mode="standalone",
            crawler_script_ref=str(script),
            manifest_ref=str(manifest),
        )
    )

    runtime.frontier.seed(
        FrontierSeedRequest(
            urls=[
                "https://example.com/item/1#frag",
                "https://example.com/item/1",
            ]
        )
    )

    frontier_items = runtime.store.list_frontier_items("example.com")
    assert len(frontier_items) == 1

    created = runtime.scheduler.dispatch_frontier(limit=10)
    assert len(created) == 1
    assert len(runtime.store.list_jobs(JobType.CRAWL)) == 1


@pytest.mark.asyncio
async def test_crawl_worker_executes_standalone_adapter_and_stores_result(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    script = tmp_path / "crawler.py"
    manifest = tmp_path / "crawler_manifest.json"
    _write_demo_crawler(script)
    manifest.write_text("{}", encoding="utf-8")
    runtime.store.register_adapter_version(
        AdapterVersion(
            site_key="example.com",
            version="v1",
            output_mode="standalone",
            crawler_script_ref=str(script),
            manifest_ref=str(manifest),
        )
    )
    runtime.control.submit_crawl_job(
        CrawlJobSpec(
            site_url="https://example.com/item/1",
            source_url="https://example.com/item/1",
            adapter_version="v1",
            action="page",
        )
    )

    worker = CrawlWorker(runtime)
    assert await worker.run_once() is True

    results = runtime.store.list_results()
    assert len(results) == 1
    assert results[0].normalized_payload["url"] == "https://example.com/item/1"
    assert results[0].normalized_payload["action"] == "page"


@pytest.mark.asyncio
async def test_crawl_worker_delegates_bridge_jobs(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    script = tmp_path / "crawler.py"
    manifest = tmp_path / "crawler_manifest.json"
    _write_demo_crawler(script, bridge=True)
    manifest.write_text("{}", encoding="utf-8")
    runtime.store.register_adapter_version(
        AdapterVersion(
            site_key="example.com",
            version="bridge-v1",
            output_mode="bridge",
            crawler_script_ref=str(script),
            manifest_ref=str(manifest),
        )
    )
    runtime.control.submit_crawl_job(
        CrawlJobSpec(
            site_url="https://example.com/item/2",
            source_url="https://example.com/item/2",
            adapter_version="bridge-v1",
            action="page",
        )
    )

    worker = CrawlWorker(runtime)
    assert await worker.run_once() is True

    crawl_jobs = runtime.store.list_jobs(JobType.CRAWL)
    bridge_jobs = runtime.store.list_jobs(JobType.BRIDGE)
    assert crawl_jobs[0].status.value == "delegated"
    assert len(bridge_jobs) == 1


def test_resource_manager_prefers_browser_sticky_proxy_for_bridge(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    runtime.resources.upsert_proxy(
        ProxyRecord(
            proxy_id="proxy-plain",
            provider="local",
            region="global",
            protocol="http",
            endpoint="http://plain.proxy:8080",
            status=ProxyStatus.ACTIVE,
            supports_browser=False,
            sticky_capable=False,
        )
    )
    runtime.resources.upsert_proxy(
        ProxyRecord(
            proxy_id="proxy-browser",
            provider="local",
            region="global",
            protocol="http",
            endpoint="http://browser.proxy:8080",
            status=ProxyStatus.ACTIVE,
            supports_browser=True,
            sticky_capable=True,
        )
    )

    lease = runtime.resources.lease_proxy(
        site_key="example.com",
        job_type=JobType.BRIDGE,
        job_id="job-001",
        requires_browser=True,
        sticky_required=True,
    )

    assert lease is not None
    assert lease.resource_id == "proxy-browser"


@pytest.mark.asyncio
async def test_reverse_worker_registers_adapter_version(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    crawler = generated_dir / "crawler.py"
    manifest = generated_dir / "crawler_manifest.json"
    report = generated_dir / "run_report.json"
    captured = {}
    _write_demo_crawler(crawler)
    manifest.write_text("{}", encoding="utf-8")
    report.write_text("{}", encoding="utf-8")

    class FakeOrchestrator:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return MasterResult(
                session_id="rev01",
                url=kwargs["url"],
                completed=True,
                verified=True,
                analysis=AnalysisResult(session_id="rev01"),
                generated=GeneratedCode(
                    session_id="rev01",
                    output_mode="standalone",
                    crawler_script_path=crawler,
                    manifest_path=manifest,
                    verified=True,
                ),
                report_path=report,
            )

    runtime.control.submit_reverse_job(ReverseJobSpec(url="https://example.com/start", goal="test reverse"))

    worker = ReverseWorker(runtime, orchestrator_factory=FakeOrchestrator)
    assert await worker.run_once() is True

    adapters = runtime.store.list_adapters("example.com")
    assert len(adapters) == 1
    assert adapters[0].verified_at is not None
    reverse_job = runtime.store.list_jobs(JobType.REVERSE)[0]
    assert captured["session_id"] == reverse_job.job_id


@pytest.mark.asyncio
async def test_crawl_worker_uses_full_job_id_as_target_session_id(tmp_path):
    runtime = PlatformRuntime(workspace=tmp_path)
    script = tmp_path / "crawler.py"
    manifest = tmp_path / "crawler_manifest.json"
    _write_demo_crawler(script)
    manifest.write_text("{}", encoding="utf-8")
    runtime.store.register_adapter_version(
        AdapterVersion(
            site_key="example.com",
            version="v1",
            output_mode="standalone",
            crawler_script_ref=str(script),
            manifest_ref=str(manifest),
        )
    )
    runtime.control.submit_crawl_job(
        CrawlJobSpec(
            site_url="https://example.com/item/1",
            source_url="https://example.com/item/1",
            adapter_version="v1",
            action="page",
        )
    )

    captured = {}

    async def fake_execute(script_path, target, **kwargs):
        captured["session_id"] = target.session_id

        class Result:
            headers = {}
            crawl_data = {"ok": True}
            output_path = None
            error = None

        return Result()

    worker = CrawlWorker(runtime)
    worker._replayer.execute_crawl_subprocess = fake_execute  # type: ignore[method-assign]

    assert await worker.run_once() is True

    crawl_job = runtime.store.list_jobs(JobType.CRAWL)[0]
    assert captured["session_id"] == crawl_job.job_id


@pytest.mark.asyncio
async def test_session_refresh_worker_uses_full_job_id_for_state_paths(tmp_path, monkeypatch):
    runtime = PlatformRuntime(workspace=tmp_path)
    account = runtime.resources.upsert_account(
        AccountRecord(
            account_id="acct-001",
            site_key="example.com",
            credential_ref="secret://acct-001",
        )
    )

    runtime.control.submit_session_refresh_job(
        SessionRefreshJobSpec(
            account_id=account.account_id,
            refresh_url="https://example.com/login",
        )
    )

    captured = {}

    class FakePage:
        async def goto(self, url, wait_until=None):
            captured["goto_url"] = url
            captured["wait_until"] = wait_until

    class FakeBrowserDriver:
        def __init__(self, *args, **kwargs):
            self.context = object()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def launch(self, profile, session_state=None):
            captured["launched"] = True
            return FakePage()

    class FakeBrowserStateStore:
        def __init__(self, store):
            self._store = store

        async def persist_context(self, session_id, domain, context, state):
            captured["persist_session_id"] = session_id
            return state

    monkeypatch.setattr("axelo.platform.workers.BrowserDriver", FakeBrowserDriver)
    monkeypatch.setattr("axelo.platform.workers.BrowserStateStore", FakeBrowserStateStore)

    worker = SessionRefreshWorker(runtime)
    assert await worker.run_once() is True

    refresh_job = runtime.store.list_jobs(JobType.SESSION_REFRESH)[0]
    updated_account = runtime.store.get_account(account.account_id)
    assert updated_account is not None
    assert captured["persist_session_id"] == refresh_job.job_id
    session_state_path = Path(updated_account.session_state_ref)
    assert session_state_path.parent.name == refresh_job.job_id
    assert session_state_path.name == "session_state.json"
