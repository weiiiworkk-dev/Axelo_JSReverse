from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

from axelo.config import settings
from axelo.models.target import RequestCapture, TargetSite

log = structlog.get_logger()

WORKER_SCRIPT = Path(__file__).with_name("subprocess_worker.py")
_REPLAY_HEADER_BLACKLIST = {
    "content-length",
    "transfer-encoding",
    "host",
    "cookie",            # managed separately via session state
    "authorization",     # prevent credential leakage across sessions
    "if-none-match",     # ETag replay causes spurious 304
    "if-modified-since", # same
}


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
        temp_dir = Path(tempfile.mkdtemp(prefix="verify-", dir=runtime_root))
        result: dict[str, Any] | None = None
        execution_error: str | None = None
        try:
            copied_script = temp_dir / script_path.name
            shutil.copy2(script_path, copied_script)

            # Locate the bridge server — it may be plain "bridge_server.js" or
            # prefixed with the session-id (e.g. "AAA-000004_bridge_server.js").
            # Always copy it into temp_dir as "bridge_server.js" so the
            # crawler template's hardcoded BRIDGE_PATH = "bridge_server.js" resolves.
            sibling_bridge = script_path.parent / "bridge_server.js"
            if not sibling_bridge.exists():
                candidates = sorted(script_path.parent.glob("*_bridge_server.js"))
                if candidates:
                    sibling_bridge = candidates[0]
            if sibling_bridge.exists():
                shutil.copy2(sibling_bridge, temp_dir / "bridge_server.js")

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
                execution_error = f"script execution timed out after {timeout:.1f}s"
            else:
                if not result_path.exists():
                    stderr_text = stderr.decode("utf-8", errors="replace").strip()
                    stdout_text = stdout.decode("utf-8", errors="replace").strip()
                    details = stderr_text or stdout_text or f"worker exited with code {process.returncode}"
                    execution_error = f"script execution failed: {details[:500]}"
                else:
                    try:
                        result = json.loads(result_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError) as exc:
                        execution_error = f"script execution produced invalid output: {exc}"
        finally:
            self._cleanup_runtime_dir(temp_dir)

        if execution_error:
            return CrawlExecutionResult(error=execution_error)
        if result is None:
            return CrawlExecutionResult(error="script execution produced no result")
        return CrawlExecutionResult(
            headers=result.get("headers") or {},
            crawl_data=result.get("crawl_data"),
            output_path=result.get("output_path"),
            error=result.get("error"),
        )

    def _cleanup_runtime_dir(self, temp_dir: Path, *, retries: int = 6, base_delay_sec: float = 0.25) -> None:
        if not temp_dir.exists():
            return
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                shutil.rmtree(temp_dir)
                return
            except FileNotFoundError:
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(base_delay_sec * (attempt + 1))
            except OSError as exc:
                last_error = exc
                break
        log.warning(
            "verify_runtime_cleanup_deferred",
            path=str(temp_dir),
            error=str(last_error) if last_error else "unknown cleanup error",
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
        merged_headers = {
            key: value
            for key, value in merged_headers.items()
            if str(key).lower() not in _REPLAY_HEADER_BLACKLIST
        }
        merged_headers = _sanitize_sec_fetch_headers(merged_headers, req.url)

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
                response_headers=dict(getattr(response, "headers", {}) or {}),
                headers=extra_headers,
            )
        except Exception as exc:
            log.warning("replay_failed", error=str(exc))
            return ReplayResult(ok=False, error=str(exc), status_code=0)


def _sanitize_sec_fetch_headers(headers: dict[str, str], target_url: str) -> dict[str, str]:
    """Remove or correct sec-fetch-* headers whose values contradict the replay context.

    A wrong sec-fetch-* header is worse than an absent one — remove rather than
    emit a semantically impossible combination that modern WAFs detect.
    """
    result = dict(headers)
    lowered = {k.lower(): k for k in result}

    sec_mode_key = lowered.get("sec-fetch-mode")
    sec_site_key = lowered.get("sec-fetch-site")
    sec_dest_key = lowered.get("sec-fetch-dest")
    origin_key = lowered.get("origin")

    sec_mode = result.get(sec_mode_key, "").lower() if sec_mode_key else ""
    sec_site = result.get(sec_site_key, "").lower() if sec_site_key else ""
    sec_dest = result.get(sec_dest_key, "").lower() if sec_dest_key else ""

    # navigate mode must pair with document destination
    if sec_mode == "navigate" and sec_dest and sec_dest not in ("document", "iframe", "frame", "embed", "object"):
        result.pop(sec_dest_key, None)

    # cors mode without Origin header is semantically invalid — drop sec-fetch-mode
    if sec_mode == "cors" and not origin_key:
        result.pop(sec_mode_key, None)
        result.pop(sec_site_key, None)

    # sec-fetch-site: same-origin with a cross-origin URL is a strong automation signal
    if sec_site == "same-origin" and sec_mode_key:
        try:
            from urllib.parse import urlparse
            origin_val = result.get(origin_key, "") if origin_key else ""
            target_origin = "{0.scheme}://{0.netloc}".format(urlparse(target_url))
            if origin_val and not target_origin.startswith(origin_val.rstrip("/")):
                result.pop(sec_site_key, None)
        except Exception:
            pass

    return result


class ReplayResult:
    def __init__(
        self,
        ok: bool,
        status_code: int = 0,
        response_body: str = "",
        headers: dict | None = None,
        response_headers: dict | None = None,
        error: str | None = None,
        output_path: str | None = None,
        generated_data: Any = None,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}
        self.response_headers = response_headers or {}
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
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC", "NODE_PATH"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["AXELO_NODE_BIN"] = os.environ.get("AXELO_NODE_BIN") or settings.node_bin

    # Ensure Node.js can resolve 'playwright' when the bridge server runs from a temp dir.
    # NODE_PATH tells Node.js to look in these directories for modules, just like node_modules
    # at the project root would be found via require() traversal.
    _project_node_modules = Path(__file__).resolve().parents[2] / "node_modules"
    if _project_node_modules.exists():
        existing_node_path = env.get("NODE_PATH", "")
        sep = os.pathsep
        env["NODE_PATH"] = str(_project_node_modules) + (sep + existing_node_path if existing_node_path else "")

    if extra_env:
        env.update(extra_env)
    return env
