from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

SCRIPTS_DIR = Path(__file__).parent / "scripts"
WORKER_SCRIPT = SCRIPTS_DIR / "worker.mjs"


class NodeRunnerError(Exception):
    pass


class NodeRunner:
    """
    管理一个持久 Node.js 子进程，通过换行分隔 JSON-RPC 通信。
    单例使用：一个 session 共享一个进程。
    """

    def __init__(self, node_bin: str = "node") -> None:
        self._node_bin = node_bin
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        if self._proc is not None:
            await self.stop()

        self._proc = await asyncio.create_subprocess_exec(
            self._node_bin,
            str(WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(SCRIPTS_DIR),
        )

        init_msg = await self._wait_for_ready()
        if not init_msg.get("result", {}).get("ready"):
            raise NodeRunnerError(f"Node worker 启动失败: {init_msg}")

        self._reader_task = asyncio.create_task(self._reader_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        log.info("node_runner_started", pid=self._proc.pid)

    async def stop(self) -> None:
        if self._proc is None:
            return
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except Exception:
            if self._proc.returncode is None:
                self._proc.kill()
                await self._proc.wait()
        finally:
            self._reader_task = None
            self._stderr_task = None
            self._proc = None

        log.info("node_runner_stopped")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_sec: float = 60.0,
        restart_on_timeout: bool = False,
    ) -> dict:
        if self._proc is None or self._proc.returncode is not None:
            await self.start()
        if self._proc is None or self._proc.stdin is None:
            raise NodeRunnerError("NodeRunner 未启动，请先调用 start()")

        msg_id = str(uuid.uuid4())[:8]
        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})

        try:
            async with self._lock:
                self._proc.stdin.write((payload + "\n").encode())
                await self._proc.stdin.drain()
            result = await asyncio.wait_for(future, timeout=timeout_sec)
        except asyncio.TimeoutError as exc:
            self._pending.pop(msg_id, None)
            if restart_on_timeout:
                log.warning("node_call_timeout_restart", method=method, timeout_sec=timeout_sec)
                await self.restart()
            raise NodeRunnerError(f"Node 调用超时: {method}") from exc
        except (BrokenPipeError, ConnectionResetError) as exc:
            self._pending.pop(msg_id, None)
            await self.restart()
            raise NodeRunnerError(f"Node 连接中断 [{method}]: {exc}") from exc

        if "error" in result:
            raise NodeRunnerError(f"Node 错误 [{method}]: {result['error']}")

        return result.get("result", {})

    async def _reader_loop(self) -> None:
        while self._proc and self._proc.stdout:
            try:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                if not (raw.startswith("{") and raw.endswith("}")):
                    log.debug("node_stdout_ignored", preview=raw[:120])
                    continue
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.debug("node_reader_error", error=str(exc))

    async def _stderr_loop(self) -> None:
        while self._proc and self._proc.stderr:
            try:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").strip()
                if raw:
                    log.debug("node_stderr", message=raw[:200])
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _wait_for_ready(self) -> dict:
        if self._proc is None or self._proc.stdout is None:
            raise NodeRunnerError("Node worker 未创建")

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            line = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=max(0.1, deadline - time.monotonic()),
            )
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            if not (raw.startswith("{") and raw.endswith("}")):
                log.debug("node_startup_stdout_ignored", preview=raw[:120])
                continue
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                log.debug("node_startup_json_ignored", preview=raw[:120])
                continue
        raise NodeRunnerError("Node worker 启动超时或未返回 ready 消息")

    async def deobfuscate(self, source: str, tool: str, *, timeout_sec: float = 25.0) -> dict:
        """
        去混淆源码。
        返回: {success, code, tool, originalScore, outputScore, modules, error}
        """
        return await self.call(
            "deobfuscate",
            {"source": source, "tool": tool},
            timeout_sec=timeout_sec,
            restart_on_timeout=True,
        )

    async def extract_ast(self, source: str) -> dict:
        """
        提取 AST 元数据。
        返回: {success, functions, cryptoUsages, stringLiterals, envAccess, error}
        """
        return await self.call("extractAst", {"source": source})

    async def execute_sandboxed(
        self,
        source: str,
        hook_targets: list[str],
        call_expr: str = "",
        timeout_ms: int = 5000,
    ) -> dict:
        """
        在 isolated-vm 中执行代码并记录 Hook。
        返回: {success, intercepts, result, error}
        """
        return await self.call(
            "executeSandboxed",
            {
                "source": source,
                "hookTargets": hook_targets,
                "callExpr": call_expr,
                "timeoutMs": timeout_ms,
            },
        )

    async def ping(self) -> bool:
        result = await self.call("ping")
        return result.get("pong", False)

    async def __aenter__(self) -> "NodeRunner":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
