from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import httpx
import structlog

from axelo.config import settings
from axelo.models.target import RequestCapture, TargetSite
from axelo.output import save_output

log = structlog.get_logger()


class CrawlExecutionResult:
    def __init__(
        self,
        headers: dict[str, str] | None = None,
        crawl_data: Any = None,
        output_path: str | None = None,
        error: str | None = None,
    ) -> None:
        self.headers = headers or {}
        self.crawl_data = crawl_data
        self.output_path = output_path
        self.error = error


class RequestReplayer:
    """Load generated crawler code, execute crawl(), then optionally replay one target request."""

    async def execute_crawl(
        self,
        script_path: Path,
        target: TargetSite,
    ) -> CrawlExecutionResult:
        try:
            spec = importlib.util.spec_from_file_location("axelo_gen", script_path)
            if spec is None or spec.loader is None:
                return CrawlExecutionResult(error="Unable to load generated crawler module")

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            crawler_class = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "crawl"):
                    crawler_class = obj
                    break

            if crawler_class is None:
                return CrawlExecutionResult(error="No class exposing crawl() was found")

            instance = crawler_class()
            crawl_data = instance.crawl()
            gen_headers = getattr(instance, "_last_headers", {}) or {}
            output_path = save_output(
                crawl_data,
                target.output_format,
                settings.session_dir(target.session_id) / "output",
            )
            return CrawlExecutionResult(
                headers=gen_headers,
                crawl_data=crawl_data,
                output_path=str(output_path) if output_path else None,
            )
        except Exception as exc:
            return CrawlExecutionResult(error=f"script execution failed: {exc}")

    async def replay_with_script(
        self,
        script_path: Path,
        target: TargetSite,
        timeout: float = 15.0,
    ) -> tuple[dict[str, str], "ReplayResult"]:
        execution = await self.execute_crawl(script_path, target)
        if execution.error:
            return {}, ReplayResult(ok=False, error=execution.error, status_code=0)

        if not target.target_requests:
            return execution.headers, ReplayResult(
                ok=True,
                status_code=0,
                headers=execution.headers,
                output_path=execution.output_path,
                generated_data=execution.crawl_data,
            )

        req = target.target_requests[0]
        result = await self._send_request(req, execution.headers, timeout)
        result.output_path = execution.output_path
        result.generated_data = execution.crawl_data
        return execution.headers, result

    async def _send_request(
        self,
        req: RequestCapture,
        extra_headers: dict[str, str],
        timeout: float,
    ) -> "ReplayResult":
        merged_headers = dict(req.request_headers)
        merged_headers.update(extra_headers)
        for header in ("content-length", "transfer-encoding", "host"):
            merged_headers.pop(header, None)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=req.method,
                    url=req.url,
                    headers=merged_headers,
                    content=req.request_body,
                )
            ok = 200 <= response.status_code < 400
            log.info("replay_done", url=req.url[:120], status=response.status_code, ok=ok)
            return ReplayResult(
                ok=ok,
                status_code=response.status_code,
                response_body=response.text[:2000],
                headers=extra_headers,
            )
        except Exception as exc:
            log.warning("replay_failed", error=str(exc))
            return ReplayResult(ok=False, error=str(exc), status_code=0)


class ReplayResult:
    def __init__(
        self,
        ok: bool,
        status_code: int = 0,
        response_body: str = "",
        headers: dict | None = None,
        error: str | None = None,
        output_path: str | None = None,
        generated_data: Any = None,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}
        self.error = error
        self.output_path = output_path
        self.generated_data = generated_data

    def summary(self) -> str:
        if self.error:
            return f"replay failed: {self.error}"
        icon = "ok" if self.ok else "fail"
        output_note = f" | output={self.output_path}" if self.output_path else ""
        return f"{icon} HTTP {self.status_code} | preview={self.response_body[:200]}{output_note}"
