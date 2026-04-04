from __future__ import annotations

import asyncio
import sys
from typing import Optional

import structlog
import typer
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from axelo.config import settings
from axelo.models.run_config import RunConfig
from axelo.modes.registry import available_modes
from axelo.orchestrator.master import MasterOrchestrator
from axelo.presentation import verification_status_markup, verification_was_skipped
from axelo.storage.session_store import SessionStore
from axelo.platform.models import FrontierSeedRequest, ReverseJobSpec, CrawlJobSpec, SessionRefreshJobSpec
from axelo.platform.runtime import PlatformRuntime
from axelo.platform.workers import worker_from_type

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="axelo",
    help="AI 驱动的网页 JS 逆向系统",
    no_args_is_help=True,
)
console = Console()
submit_app = typer.Typer(help="提交平台化作业")
frontier_app = typer.Typer(help="管理 URL frontier")
worker_app = typer.Typer(help="运行平台 worker")
serve_app = typer.Typer(help="运行平台服务")
app.add_typer(submit_app, name="submit")
app.add_typer(frontier_app, name="frontier")
app.add_typer(worker_app, name="worker")
app.add_typer(serve_app, name="serve")


def _setup_logging(log_level: str) -> None:
    import logging

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
    )


def _parse_login_state(login_state: str) -> bool | None:
    value = login_state.strip().lower()
    if value in {"cookie", "yes", "true"}:
        return True
    if value in {"no", "false"}:
        return False
    return None


def _platform_runtime() -> PlatformRuntime:
    return PlatformRuntime.from_settings()


@app.command()
def run(
    url: str = typer.Argument(..., help="目标网站 URL"),
    goal: str = typer.Option(
        "分析并复现请求签名/Token 生成逻辑",
        "--goal",
        "-g",
        help="逆向目标描述，越具体越好",
    ),
    target_hint: str = typer.Option(
        "",
        "--target-hint",
        help="目标对象提示，如商品 URL、SKU、搜索词、店铺名或类目名",
    ),
    use_case: str = typer.Option(
        "research",
        "--use-case",
        help="用途说明: research/internal/partner/debug",
    ),
    authorization_status: str = typer.Option(
        "pending",
        "--authorization-status",
        help="授权状态: authorized/pending/unauthorized",
    ),
    replay_mode: str = typer.Option(
        "discover_only",
        "--replay-mode",
        help="回放模式: discover_only/authorized_replay/official_api_only",
    ),
    mode: str = typer.Option(
        "interactive",
        "--mode",
        "-m",
        help=f"运行模式: {available_modes()}",
    ),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="会话 ID，用于续跑"),
    resume: bool = typer.Option(False, "--resume", "-r", help="从上次进度继续"),
    budget: float = typer.Option(2.0, "--budget", "-b", help="最大 AI 费用预算（USD）"),
    known_endpoint: str = typer.Option("", "--known-endpoint", help="已知 API 路径，如 /api/search"),
    antibot_type: str = typer.Option(
        "unknown",
        "--antibot",
        help="反爬类型: cloudflare/datadome/akamai/custom/unknown",
    ),
    login_state: str = typer.Option(
        "unknown",
        "--login",
        help="登录需求: no/cookie/unknown",
    ),
    output_format: str = typer.Option(
        "print",
        "--output-format",
        help="输出格式: json_file/csv/print/custom",
    ),
    crawl_rate: str = typer.Option(
        "standard",
        "--crawl-rate",
        help="频率偏好: conservative/standard/aggressive",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        help="浏览器环境模拟 profile 名称",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        help="覆盖 interaction simulation 的 pointer default seed",
    ),
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动 JS 逆向流水线。"""
    _setup_logging(log_level)
    from axelo.browser.profiles import PROFILES

    if profile not in PROFILES:
        choices = ", ".join(sorted(PROFILES.keys()))
        console.print(
            f"[bold red]无效的 profile[/bold red]: {profile}\n"
            f"[dim]可选值: {choices}[/dim]"
        )
        raise typer.Exit(code=2)

    selected_profile = PROFILES[profile].model_copy(deep=True)
    if seed is not None:
        selected_profile.interaction_simulation.pointer.default_seed = seed

    try:
        run_cfg = RunConfig(
            url=url,
            goal=goal,
            target_hint=target_hint,
            use_case=use_case,
            authorization_status=authorization_status,
            replay_mode=replay_mode,
            mode_name=mode,
            budget_usd=budget,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=_parse_login_state(login_state),
            output_format=output_format,
            crawl_rate=crawl_rate,
        )
    except ValidationError as exc:
        console.print(f"[bold red]参数校验失败[/bold red]\n{exc}")
        raise typer.Exit(code=2)

    effective_seed = selected_profile.interaction_simulation.pointer.default_seed
    console.print(
        Panel(
            f"[white]目标 URL:[/white] [yellow]{run_cfg.url}[/yellow]\n"
            f"[white]模式:[/white] [green]{run_cfg.mode_name.value}[/green]  "
            f"[white]预算:[/white] [cyan]${run_cfg.budget_usd}[/cyan]\n"
            f"[white]逆向任务:[/white] {run_cfg.goal}\n"
            f"[white]目标对象:[/white] {run_cfg.target_hint or '未指定'}\n"
            f"[white]用途/授权:[/white] {run_cfg.use_case.value} / {run_cfg.authorization_status.value}\n"
            f"[white]回放模式:[/white] {run_cfg.replay_mode.value}\n"
            f"[white]Profile / Seed:[/white] {profile} / {effective_seed}\n"
            f"[white]成本策略:[/white] balanced",
            title="[bold cyan]Axelo JSReverse[/bold cyan]",
            border_style="cyan",
        )
    )

    orchestrator = MasterOrchestrator()
    kwargs = run_cfg.orchestrator_kwargs()
    kwargs["session_id"] = session_id
    kwargs["resume"] = resume
    kwargs["browser_profile"] = selected_profile
    result = asyncio.run(orchestrator.run(**kwargs))

    if result.completed:
        if verification_was_skipped(result):
            console.print(f"\n[bold cyan]✓ 流程完成（验证已跳过）[/bold cyan]  会话: [cyan]{result.session_id}[/cyan]")
        else:
            console.print(f"\n[bold green]✓ 逆向完成[/bold green]  会话: [cyan]{result.session_id}[/cyan]")
        if result.difficulty:
            console.print(
                f"难度: [yellow]{result.difficulty.level}[/yellow]  "
                f"验证: {verification_status_markup(result)}"
            )
        if result.execution_plan:
            console.print(
                f"路径: [cyan]{result.route_label or result.execution_plan.route_label}[/cyan]  "
                f"预估成本: [yellow]{result.execution_plan.estimated_cost_range}[/yellow]"
            )
            if result.execution_plan.degradation_notes:
                console.print(f"[dim]降级原因: {' | '.join(result.execution_plan.degradation_notes)}[/dim]")
            elif result.execution_plan.reasons:
                console.print(f"[dim]路径原因: {' | '.join(result.execution_plan.reasons[:2])}[/dim]")
        if result.reuse_hits:
            console.print(f"[dim]复用命中: {', '.join(result.reuse_hits)}[/dim]")
        if result.output_dir:
            console.print(f"输出: [cyan]{result.output_dir}[/cyan]")
        if result.cost:
            console.print(f"[dim]{result.cost.summary()}[/dim]")
        if result.report_path:
            console.print(f"[dim]报告: {result.report_path}[/dim]")
    else:
        console.print(f"\n[bold red]✗ 未完成[/bold red]: {result.error or '未知错误'}")
        console.print(f"续跑: [dim]axelo run {run_cfg.url} --resume --session {result.session_id}[/dim]")


@app.command()
def sessions() -> None:
    """列出所有历史会话。"""
    store = SessionStore(settings.sessions_dir)
    session_ids = store.list_sessions()

    if not session_ids:
        console.print("[dim]暂无历史会话[/dim]")
        return

    table = Table(title="历史会话", box=box.ROUNDED)
    table.add_column("Session ID", style="cyan")
    for sid in session_ids:
        table.add_row(sid)
    console.print(table)


@app.command()
def patterns() -> None:
    """显示内置站点模式库。"""
    from axelo.patterns.common import KNOWN_PROFILES

    table = Table(title="内置站点模式库", box=box.ROUNDED)
    table.add_column("分类", style="cyan")
    table.add_column("典型算法", style="white")
    table.add_column("难度", style="yellow")
    table.add_column("策略", style="green")
    for profile in KNOWN_PROFILES:
        table.add_row(profile.category, profile.typical_algorithm, profile.difficulty, profile.strategy)
    console.print(table)


@app.command()
def info() -> None:
    """显示系统配置和记忆库统计。"""
    table = Table(title="Axelo 配置", box=box.ROUNDED)
    table.add_column("配置项", style="cyan")
    table.add_column("值", style="white")

    rows = [
        ("模型", settings.model),
        ("浏览器", settings.browser),
        ("无头模式", str(settings.headless)),
        ("工作目录", str(settings.workspace)),
        ("Node.js", settings.node_bin),
        ("API Key", "[green]已配置[/green]" if settings.anthropic_api_key else "[red]未配置[/red]"),
    ]
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)

    try:
        mem_dir = settings.workspace / "memory"
        db_path = mem_dir / "axelo.db"
        if db_path.exists():
            from axelo.memory.db import MemoryDB

            db = MemoryDB(db_path)
            sessions_list = db.get_similar_sessions("")
            console.print(f"\n[dim]记忆库: {db_path} | 历史会话: {len(sessions_list)} 条[/dim]")
    except Exception:
        pass


@submit_app.command("reverse")
def submit_reverse(
    url: str = typer.Argument(..., help="目标站点 URL"),
    goal: str = typer.Option("分析并复现请求签名/Token 生成逻辑", "--goal", "-g", help="逆向目标"),
    target_hint: str = typer.Option("", "--target-hint", help="目标对象提示"),
    known_endpoint: str = typer.Option("", "--known-endpoint", help="已知 API 路径"),
    antibot_type: str = typer.Option("unknown", "--antibot", help="反爬类型"),
    login_state: str = typer.Option("unknown", "--login", help="登录需求: no/cookie/unknown"),
    browser_profile_name: str = typer.Option("default", "--profile", help="浏览器环境 profile"),
    budget: float = typer.Option(2.0, "--budget", help="逆向预算"),
) -> None:
    runtime = _platform_runtime()
    job = runtime.control.submit_reverse_job(
        ReverseJobSpec(
            url=url,
            goal=goal,
            target_hint=target_hint,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=_parse_login_state(login_state),
            browser_profile_name=browser_profile_name,
            budget_usd=budget,
        )
    )
    console.print(f"[green]reverse job submitted[/green] {job.job_id}")


@submit_app.command("crawl")
def submit_crawl(
    site_url: str = typer.Argument(..., help="站点或详情页 URL"),
    adapter_version: str = typer.Option("", "--adapter-version", help="指定 adapter 版本"),
    action: str = typer.Option("page", "--action", help="page/request/observed/known_endpoint"),
    dataset_name: str = typer.Option("default", "--dataset", help="目标数据集"),
    account_id: str = typer.Option("", "--account", help="绑定账号"),
    proxy_id: str = typer.Option("", "--proxy", help="绑定代理"),
) -> None:
    runtime = _platform_runtime()
    job = runtime.control.submit_crawl_job(
        CrawlJobSpec(
            site_url=site_url,
            source_url=site_url,
            adapter_version=adapter_version,
            action=action,
            dataset_name=dataset_name,
            account_id=account_id,
            proxy_id=proxy_id,
        )
    )
    console.print(f"[green]crawl job submitted[/green] {job.job_id}")


@submit_app.command("session-refresh")
def submit_session_refresh(
    refresh_url: str = typer.Argument(..., help="刷新 session 的页面 URL"),
    account_id: str = typer.Option(..., "--account", help="账号 ID"),
    browser_profile_name: str = typer.Option("default", "--profile", help="浏览器环境 profile"),
) -> None:
    runtime = _platform_runtime()
    job = runtime.control.submit_session_refresh_job(
        SessionRefreshJobSpec(
            account_id=account_id,
            refresh_url=refresh_url,
            browser_profile_name=browser_profile_name,
        )
    )
    console.print(f"[green]session refresh job submitted[/green] {job.job_id}")


@frontier_app.command("seed")
def frontier_seed(
    urls: list[str] = typer.Argument(..., help="待种入 frontier 的 URL 列表"),
    site_key: str = typer.Option("", "--site-key", help="站点标识"),
    adapter_version: str = typer.Option("", "--adapter-version", help="绑定 adapter 版本"),
    priority: int = typer.Option(100, "--priority", help="优先级，数值越小越高"),
    depth: int = typer.Option(0, "--depth", help="frontier 深度"),
) -> None:
    runtime = _platform_runtime()
    items = runtime.frontier.seed(
        FrontierSeedRequest(
            urls=urls,
            site_key=site_key,
            adapter_version=adapter_version,
            priority=priority,
            depth=depth,
        )
    )
    console.print(f"[green]seeded frontier items[/green] {len(items)}")


@worker_app.command("run")
def worker_run(
    worker_type: str = typer.Option(..., "--type", help="reverse-worker/crawl-worker/bridge-worker/session-refresh-worker"),
    queue_name: str = typer.Option("default", "--queue", help="队列名"),
    region: str = typer.Option("global", "--region", help="区域"),
    once: bool = typer.Option(False, "--once", help="只处理一次"),
    limit: Optional[int] = typer.Option(None, "--limit", help="处理上限"),
    poll_interval: float = typer.Option(settings.platform_poll_interval_sec, "--poll-interval", help="空轮询等待秒数"),
) -> None:
    runtime = _platform_runtime()
    worker = worker_from_type(runtime, worker_type, queue_name=queue_name, region=region)
    if once:
        processed = asyncio.run(worker.run_once())
        raise typer.Exit(code=0 if processed else 1)
    asyncio.run(worker.run_forever(poll_interval=poll_interval, limit=limit))


@serve_app.command("scheduler")
def serve_scheduler(
    once: bool = typer.Option(False, "--once", help="只调度一次"),
    limit: int = typer.Option(100, "--limit", help="单次调度条数"),
    poll_interval: float = typer.Option(settings.platform_poll_interval_sec, "--poll-interval", help="轮询秒数"),
) -> None:
    runtime = _platform_runtime()
    if once:
        created = runtime.scheduler.dispatch_frontier(limit=limit)
        console.print(f"[green]scheduler dispatched[/green] {len(created)} jobs")
        return

    async def _loop() -> None:
        while True:
            runtime.scheduler.dispatch_frontier(limit=limit)
            await asyncio.sleep(poll_interval)

    asyncio.run(_loop())


@serve_app.command("control-api")
def serve_control_api(
    host: str = typer.Option(settings.control_api_host, "--host", help="监听地址"),
    port: int = typer.Option(settings.control_api_port, "--port", help="监听端口"),
) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        console.print("[bold red]缺少 optional 依赖[/bold red]，请安装 `pip install .[platform]`")
        raise typer.Exit(code=2) from exc

    from axelo.platform.control_api import create_control_app

    uvicorn.run(create_control_app(_platform_runtime()), host=host, port=port)


if __name__ == "__main__":
    app()
