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
from axelo.storage.session_store import SessionStore

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="axelo",
    help="AI 驱动的网页 JS 逆向系统",
    no_args_is_help=True,
)
console = Console()


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
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动 JS 逆向流水线。"""
    _setup_logging(log_level)

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

    console.print(
        Panel(
            f"[white]目标 URL:[/white] [yellow]{run_cfg.url}[/yellow]\n"
            f"[white]模式:[/white] [green]{run_cfg.mode_name.value}[/green]  "
            f"[white]预算:[/white] [cyan]${run_cfg.budget_usd}[/cyan]\n"
            f"[white]逆向任务:[/white] {run_cfg.goal}\n"
            f"[white]目标对象:[/white] {run_cfg.target_hint or '未指定'}\n"
            f"[white]用途/授权:[/white] {run_cfg.use_case.value} / {run_cfg.authorization_status.value}\n"
            f"[white]回放模式:[/white] {run_cfg.replay_mode.value}",
            title="[bold cyan]Axelo JSReverse[/bold cyan]",
            border_style="cyan",
        )
    )

    orchestrator = MasterOrchestrator()
    kwargs = run_cfg.orchestrator_kwargs()
    kwargs["session_id"] = session_id
    kwargs["resume"] = resume
    result = asyncio.run(orchestrator.run(**kwargs))

    if result.completed:
        console.print(f"\n[bold green]✓ 逆向完成[/bold green]  会话: [cyan]{result.session_id}[/cyan]")
        if result.difficulty:
            console.print(
                f"难度: [yellow]{result.difficulty.level}[/yellow]  "
                f"验证: {'[green]通过[/green]' if result.verified else '[red]未通过[/red]'}"
            )
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


if __name__ == "__main__":
    app()
