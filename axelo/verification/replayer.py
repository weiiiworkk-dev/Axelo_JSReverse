from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
import structlog

from axelo.config import settings
from axelo.models.target import RequestCapture, TargetSite

log = structlog.get_logger()

WORKER_SCRIPT = Path(__file__).with_name("subprocess_worker.py")


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
    """Execute generated crawler code in a subprocess, then optionally replay one target request."""

    async def execute_crawl(
        self,
        script_path: Path,
        target: TargetSite,
    ) -> CrawlExecutionResult:
        return await self.execute_crawl_subprocess(script_path, target)

    async def execute_crawl_subprocess(
        self,
        script_path: Path,
        target: TargetSite,
        timeout: float | None = None,
        crawl_kwargs: dict[str, Any] | None = None,
        init_kwargs: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> CrawlExecutionResult:
        if not script_path.exists():
            return CrawlExecutionResult(error="generated crawler file is missing")

        timeout = timeout or settings.verification_subprocess_timeout_sec
        runtime_root = (output_dir or settings.session_dir(target.session_id) / "verification_runtime")
        runtime_root.mkdir(parents=True, exist_ok=True)

        payload = {
            "session_id": target.session_id,
            "output_format": target.output_format,
            "crawl_kwargs": crawl_kwargs or {},
            "init_kwargs": init_kwargs or {},
            "output_dir": str(output_dir) if output_dir else "",
        }

        with tempfile.TemporaryDirectory(prefix="verify-", dir=runtime_root) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            copied_script = temp_dir / script_path.name
            shutil.copy2(script_path, copied_script)

            sibling_bridge = script_path.parent / "bridge_server.js"
            if sibling_bridge.exists():
                shutil.copy2(sibling_bridge, temp_dir / sibling_bridge.name)

            payload_path = temp_dir / "payload.json"
            result_path = temp_dir / "result.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(WORKER_SCRIPT),
                str(copied_script),
                str(payload_path),
                str(result_path),
                cwd=str(temp_dir),
                env=_verification_env(extra_env),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return CrawlExecutionResult(error=f"script execution timed out after {timeout:.1f}s")

            if not result_path.exists():
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                stdout_text = stdout.decode("utf-8", errors="replace").strip()
                details = stderr_text or stdout_text or f"worker exited with code {process.returncode}"
                return CrawlExecutionResult(error=f"script execution failed: {details[:500]}")

            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                return CrawlExecutionResult(error=f"script execution produced invalid output: {exc}")

        return CrawlExecutionResult(
            headers=result.get("headers") or {},
            crawl_data=result.get("crawl_data"),
            output_path=result.get("output_path"),
            error=result.get("error"),
        )

    async def replay_with_script(
        self,
        script_path: Path,
        target: TargetSite,
        timeout: float = 15.0,
        crawl_kwargs: dict[str, Any] | None = None,
        init_kwargs: dict[str, Any] | None = None,
        output_dir: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], "ReplayResult"]:
        execution = await self.execute_crawl_subprocess(
            script_path,
            target,
            timeout=timeout,
            crawl_kwargs=crawl_kwargs,
            init_kwargs=init_kwargs,
            output_dir=output_dir,
            extra_env=extra_env,
        )
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


def _verification_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    if extra_env:
        env.update(extra_env)
    return env
