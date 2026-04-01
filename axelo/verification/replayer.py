from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import structlog

from axelo.config import settings
from axelo.models.target import RequestCapture, TargetSite
from axelo.output import save_output

log = structlog.get_logger()


class RequestReplayer:
    """
    Load generated crawler code, execute crawl(), and replay one target request.
    """

    async def replay_with_script(
        self,
        script_path: Path,
        target: TargetSite,
        timeout: float = 15.0,
    ) -> tuple[dict[str, str], "ReplayResult"]:
        gen_headers: dict[str, str] = {}
        output_path: Path | None = None

        try:
            spec = importlib.util.spec_from_file_location("axelo_gen", script_path)
            if spec is None or spec.loader is None:
                return {}, ReplayResult(ok=False, error="无法加载脚本模块", status_code=0)

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            crawler_class = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "crawl"):
                    crawler_class = obj
                    break

            if crawler_class is None:
                return {}, ReplayResult(ok=False, error="未找到 crawl() 方法", status_code=0)

            instance = crawler_class()
            crawl_data = instance.crawl()
            gen_headers = getattr(instance, "_last_headers", {}) or {}
            output_path = save_output(
                crawl_data,
                target.output_format,
                settings.session_dir(target.session_id) / "output",
            )
        except Exception as exc:
            return {}, ReplayResult(ok=False, error=f"脚本加载/执行失败: {exc}", status_code=0)

        if not target.target_requests:
            return gen_headers, ReplayResult(
                ok=True,
                status_code=0,
                headers=gen_headers,
                output_path=str(output_path) if output_path else None,
            )

        req = target.target_requests[0]
        result = await self._send_request(req, gen_headers, timeout)
        result.output_path = str(output_path) if output_path else None
        return gen_headers, result

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
                resp = await client.request(
                    method=req.method,
                    url=req.url,
                    headers=merged_headers,
                    content=req.request_body,
                )
            ok = 200 <= resp.status_code < 400
            log.info("replay_done", url=req.url[:120], status=resp.status_code, ok=ok)
            return ReplayResult(
                ok=ok,
                status_code=resp.status_code,
                response_body=resp.text[:2000],
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
    ):
        self.ok = ok
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}
        self.error = error
        self.output_path = output_path

    def summary(self) -> str:
        if self.error:
            return f"✗ 请求失败: {self.error}"
        icon = "✓" if self.ok else "✗"
        output_note = f" | 输出: {self.output_path}" if self.output_path else ""
        return f"{icon} HTTP {self.status_code} | 响应前200字符: {self.response_body[:200]}{output_note}"

