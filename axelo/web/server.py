"""Axelo Web Server — 独立 FastAPI 服务，端口默认 7788。

启动方式:
    axelo web                  # 默认端口 7788
    axelo web --port 9090      # 自定义端口
    axelo web --open           # 自动在浏览器打开

提供:
    GET  /api/sessions                     — 会话列表
    GET  /api/sessions/{id}                — 会话详情
    GET  /api/sessions/{id}/events         — 增量事件（轮询备用）
    WS   /ws/sessions/{id}/stream          — 实时事件流
    POST /api/mission/start                — 启动任务
    POST /api/mission/stop                 — 停止任务
    GET  /                                 — 前端 SPA（ui/dist/）
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from axelo.web.event_broadcaster import EventBroadcaster
from axelo.web.session_watcher import SessionWatcher
from axelo.web.routes import sessions as sessions_router
from axelo.web.routes import ws as ws_router
from axelo.web.routes import mission_intake as mission_router

log = structlog.get_logger()

_UI_DIST = Path(__file__).parent / "ui" / "dist"


def create_app() -> FastAPI:
    broadcaster = EventBroadcaster()
    watcher = SessionWatcher(broadcaster)

    app = FastAPI(
        title="Axelo Web",
        description="Axelo JSReverse 可视化控制台",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inject deps into WS router
    ws_router.init(broadcaster, watcher)

    # ── Health check (always first, no filesystem dependency) ─────
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Register all API routers FIRST ────────────────────────────
    # Must come before any static file mounts or catch-all routes
    # so that POST /api/... routes are found correctly.
    app.include_router(sessions_router.router, prefix="")
    app.include_router(ws_router.router, prefix="")
    app.include_router(mission_router.router, prefix="")

    # ── Static assets ─────────────────────────────────────────────
    if _UI_DIST.exists() and (_UI_DIST / "index.html").exists():
        _assets = _UI_DIST / "assets"
        if _assets.exists():
            app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

        @app.get("/", include_in_schema=False)
        async def spa_root() -> FileResponse:
            return FileResponse(str(_UI_DIST / "index.html"), media_type="text/html")

        # SPA fallback via 404 handler — avoids the wildcard GET issue.
        # A wildcard `@app.get("/{path:path}")` causes FastAPI to report
        # 405 Method Not Allowed for POST /api/... because the path matches
        # the wildcard GET. Using a 404 handler sidesteps this entirely.
        @app.exception_handler(404)
        async def spa_404(request: Request, exc: Exception) -> FileResponse | JSONResponse:
            path = request.url.path
            # Let /api and /ws 404s bubble as JSON
            if path.startswith("/api") or path.startswith("/ws"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            # Check for exact static file
            candidate = _UI_DIST / path.lstrip("/")
            if candidate.exists() and candidate.is_file():
                return FileResponse(str(candidate))
            # SPA fallback
            return FileResponse(str(_UI_DIST / "index.html"), media_type="text/html")

        log.info("axelo_web_ui_ready", dist=str(_UI_DIST))
    else:
        @app.get("/", include_in_schema=False)
        async def no_ui() -> dict[str, Any]:
            return {
                "status": "ok",
                "message": "前端尚未构建。请在 axelo/web/ui/ 执行 npm run build",
                "docs": "/docs",
            }

    app.state.broadcaster = broadcaster
    app.state.watcher = watcher
    app.state.running_tasks = {}
    app.state.last_session_id = ""
    app.state.live_sessions = set()
    return app


async def _open_browser_delayed(port: int) -> None:
    """等待服务就绪后打开浏览器（在 uvicorn 事件循环内运行）。"""
    await asyncio.sleep(1.2)
    import webbrowser
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception as exc:
        log.warning("open_browser_failed", error=str(exc))


def run_server(port: int = 7788, open_browser: bool = False) -> None:
    """启动 uvicorn 服务（阻塞）。"""
    app = create_app()

    if open_browser:
        # 必须在 FastAPI startup 事件内创建 task，此时 uvicorn 事件循环已在运行。
        # 不能在此处调用 asyncio.ensure_future — 事件循环尚未启动。
        @app.on_event("startup")
        async def _schedule_browser_open() -> None:
            asyncio.create_task(_open_browser_delayed(port))

    log.info("axelo_web_starting", port=port, ui_ready=_UI_DIST.exists())
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
