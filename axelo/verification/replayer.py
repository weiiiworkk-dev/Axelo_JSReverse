from __future__ import annotations
import importlib.util
import sys
import asyncio
from pathlib import Path
import httpx
from axelo.models.target import RequestCapture, TargetSite
import structlog

log = structlog.get_logger()


class RequestReplayer:
    """
    使用生成的代码重放目标请求，捕获实际响应。
    支持独立脚本模式和桥接模式。
    """

    async def replay_with_script(
        self,
        script_path: Path,
        target: TargetSite,
        timeout: float = 15.0,
    ) -> tuple[dict[str, str], "ReplayResult"]:
        """
        加载生成的 Python 脚本，调用 generate()，
        再用得到的 headers 实际发送目标请求。
        返回 (generated_headers, result)。
        """
        # 动态加载
        gen_headers: dict[str, str] = {}
        load_error: str | None = None

        try:
            spec = importlib.util.spec_from_file_location("axelo_gen", script_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            gen_class = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "generate"):
                    gen_class = obj
                    break

            if gen_class is None:
                return {}, ReplayResult(ok=False, error="未找到 generate() 方法", status_code=0)

            instance = gen_class()
            for req in target.target_requests[:1]:
                body = req.request_body.decode("utf-8", errors="replace") if req.request_body else ""
                gen_headers = instance.generate(url=req.url, method=req.method, body=body)
        except Exception as e:
            return {}, ReplayResult(ok=False, error=f"脚本加载/执行失败: {e}", status_code=0)

        # 使用生成的 headers 发送真实请求
        if not target.target_requests:
            return gen_headers, ReplayResult(ok=True, status_code=0, headers=gen_headers)

        req = target.target_requests[0]
        result = await self._send_request(req, gen_headers, timeout)
        return gen_headers, result

    async def _send_request(
        self,
        req: RequestCapture,
        extra_headers: dict[str, str],
        timeout: float,
    ) -> "ReplayResult":
        merged_headers = dict(req.request_headers)
        merged_headers.update(extra_headers)
        # 移除会导致问题的头
        for h in ("content-length", "transfer-encoding", "host"):
            merged_headers.pop(h, None)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.request(
                    method=req.method,
                    url=req.url,
                    headers=merged_headers,
                    content=req.request_body,
                )
            ok = 200 <= resp.status_code < 400
            log.info("replay_done", url=req.url[:60], status=resp.status_code, ok=ok)
            return ReplayResult(
                ok=ok,
                status_code=resp.status_code,
                response_body=resp.text[:2000],
                headers=extra_headers,
            )
        except Exception as e:
            log.warning("replay_failed", error=str(e))
            return ReplayResult(ok=False, error=str(e), status_code=0)


class ReplayResult:
    def __init__(self, ok: bool, status_code: int = 0,
                 response_body: str = "", headers: dict | None = None, error: str | None = None):
        self.ok = ok
        self.status_code = status_code
        self.response_body = response_body
        self.headers = headers or {}
        self.error = error

    def summary(self) -> str:
        if self.error:
            return f"✗ 请求失败: {self.error}"
        icon = "✓" if self.ok else "✗"
        return f"{icon} HTTP {self.status_code} | 响应前200字符: {self.response_body[:200]}"
