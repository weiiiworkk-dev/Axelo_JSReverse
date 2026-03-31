from __future__ import annotations
import asyncio
import json
import os
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
    管理一个持久的 Node.js 子进程，通过换行分隔 JSON-RPC 通信。
    单例使用：一个 session 共享一个进程。
    """

    def __init__(self, node_bin: str = "node") -> None:
        self._node_bin = node_bin
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._proc is not None:
            return

        self._proc = await asyncio.create_subprocess_exec(
            self._node_bin,
            str(WORKER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(SCRIPTS_DIR),
        )

        # 等待就绪信号
        init_line = await asyncio.wait_for(self._proc.stdout.readline(), timeout=10.0)
        init_msg = json.loads(init_line)
        if not init_msg.get("result", {}).get("ready"):
            raise NodeRunnerError(f"Node worker 启动失败: {init_msg}")

        self._reader_task = asyncio.create_task(self._reader_loop())
        log.info("node_runner_started", pid=self._proc.pid)

    async def stop(self) -> None:
        if self._proc is None:
            return
        if self._reader_task:
            self._reader_task.cancel()
        try:
            self._proc.stdin.close()
            await asyncio.wait_for(self._proc.wait(), timeout=5.0)
        except Exception:
            self._proc.kill()
        self._proc = None
        log.info("node_runner_stopped")

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict:
        if self._proc is None:
            raise NodeRunnerError("NodeRunner 未启动，请先调用 start()")

        msg_id = str(uuid.uuid4())[:8]
        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})
        async with self._lock:
            self._proc.stdin.write((payload + "\n").encode())
            await self._proc.stdin.drain()

        try:
            result = await asyncio.wait_for(future, timeout=60.0)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise NodeRunnerError(f"Node 调用超时: {method}")

        if "error" in result:
            raise NodeRunnerError(f"Node 错误 [{method}]: {result['error']}")

        return result.get("result", {})

    async def _reader_loop(self) -> None:
        while self._proc and self._proc.stdout:
            try:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                msg = json.loads(line)
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("node_reader_error", error=str(e))

    # ── 高层 API ──────────────────────────────────────────────

    async def deobfuscate(self, source: str, tool: str) -> dict:
        """
        去混淆源码。
        返回: {success, code, tool, originalScore, outputScore, modules, error}
        """
        return await self.call("deobfuscate", {"source": source, "tool": tool})

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
        return await self.call("executeSandboxed", {
            "source": source,
            "hookTargets": hook_targets,
            "callExpr": call_expr,
            "timeoutMs": timeout_ms,
        })

    async def ping(self) -> bool:
        result = await self.call("ping")
        return result.get("pong", False)

    async def __aenter__(self) -> "NodeRunner":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()
