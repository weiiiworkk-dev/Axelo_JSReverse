from __future__ import annotations

from axelo.platform_.models import BridgeJobSpec, CrawlJobSpec, FrontierSeedRequest, JobType, ReverseJobSpec, SessionRefreshJobSpec
from axelo.platform_.runtime import PlatformRuntime


def create_control_app(runtime: PlatformRuntime | None = None):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install optional dependencies with `pip install .[platform]` to run the control API.") from exc

    runtime = runtime or PlatformRuntime.from_settings()
    app = FastAPI(title="Axelo Control API", version="0.1.0")

    @app.post("/v1/reverse-jobs")
    def create_reverse_job(spec: ReverseJobSpec):
        return runtime.control.submit_reverse_job(spec).model_dump(mode="json")

    @app.post("/v1/frontier/seeds")
    def create_frontier_seed(request: FrontierSeedRequest):
        return [item.model_dump(mode="json") for item in runtime.frontier.seed(request)]

    @app.post("/v1/crawl-jobs")
    def create_crawl_job(spec: CrawlJobSpec):
        return runtime.control.submit_crawl_job(spec).model_dump(mode="json")

    @app.get("/v1/adapters/{site_key}")
    def list_adapters(site_key: str):
        adapters = runtime.control.list_adapters(site_key)
        if not adapters:
            raise HTTPException(status_code=404, detail="No adapters found")
        return [item.model_dump(mode="json") for item in adapters]

    @app.post("/v1/resources/accounts/lease")
    def lease_account(site_key: str, job_type: JobType, job_id: str, region: str = "global", account_id: str = ""):
        lease = runtime.resources.lease_account(site_key=site_key, job_type=job_type, job_id=job_id, region=region, account_id=account_id)
        if lease is None:
            raise HTTPException(status_code=404, detail="No account available")
        return lease.model_dump(mode="json")

    @app.post("/v1/resources/proxies/lease")
    def lease_proxy(
        site_key: str,
        job_type: JobType,
        job_id: str,
        region: str = "global",
        proxy_id: str = "",
        requires_browser: bool = False,
        sticky_required: bool = False,
    ):
        lease = runtime.resources.lease_proxy(
            site_key=site_key,
            job_type=job_type,
            job_id=job_id,
            region=region,
            proxy_id=proxy_id,
            requires_browser=requires_browser,
            sticky_required=sticky_required,
        )
        if lease is None:
            raise HTTPException(status_code=404, detail="No proxy available")
        return lease.model_dump(mode="json")

    @app.post("/v1/session-refresh-jobs")
    def create_session_refresh_job(spec: SessionRefreshJobSpec):
        return runtime.control.submit_session_refresh_job(spec).model_dump(mode="json")

    @app.post("/v1/bridge-jobs")
    def create_bridge_job(spec: BridgeJobSpec):
        return runtime.control.submit_bridge_job(spec).model_dump(mode="json")

    return app
