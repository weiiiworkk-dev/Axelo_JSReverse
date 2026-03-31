from __future__ import annotations
import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import structlog

from axelo.orchestrator.master import MasterOrchestrator
from axelo.storage.session_store import SessionStore
from axelo.modes.registry import available_modes
from axelo.config import settings

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


@app.command()
def run(
    url: str = typer.Argument(..., help="目标网站 URL"),
    goal: str = typer.Option(
        "分析并复现请求签名/Token生成逻辑",
        "--goal", "-g",
        help="逆向目标描述（越具体越好）",
    ),
    mode: str = typer.Option(
        "interactive",
        "--mode", "-m",
        help=f"运行模式: {available_modes()}",
    ),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="会话ID（用于续跑）"),
    resume: bool = typer.Option(False, "--resume", "-r", help="从上次进度继续"),
    budget: float = typer.Option(2.0, "--budget", "-b", help="最大 AI 费用预算（USD）"),
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动 JS 逆向流水线（使用智能主编排器）"""
    _setup_logging(log_level)

    console.print(Panel(
        f"[white]目标:[/white] [yellow]{url}[/yellow]\n"
        f"[white]模式:[/white] [green]{mode}[/green]  "
        f"[white]预算:[/white] [cyan]${budget}[/cyan]\n"
        f"[white]目标:[/white] {goal}",
        title="[bold cyan]Axelo JSReverse[/bold cyan]",
        border_style="cyan",
    ))

    orchestrator = MasterOrchestrator()
    result = asyncio.run(orchestrator.run(
        url=url,
        goal=goal,
        mode_name=mode,
        session_id=session_id,
        budget_usd=budget,
        resume=resume,
    ))

    if result.completed:
        console.print(f"\n[bold green]✓ 逆向完成[/bold green]  会话: [cyan]{result.session_id}[/cyan]")
        if result.difficulty:
            console.print(f"难度: [yellow]{result.difficulty.level}[/yellow]  "
                          f"验证: {'[green]通过[/green]' if result.verified else '[red]未通过[/red]'}")
        if result.output_dir:
            console.print(f"输出: [cyan]{result.output_dir}[/cyan]")
        if result.cost:
            console.print(f"[dim]{result.cost.summary()}[/dim]")
    else:
        console.print(f"\n[bold red]✗ 未完成[/bold red]: {result.error or '未知错误'}")
        console.print(f"续跑: [dim]axelo run {url} --resume --session {result.session_id}[/dim]")


@app.command()
def sessions() -> None:
    """列出所有历史会话"""
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
    """显示内置站点模式库"""
    from axelo.patterns.common import KNOWN_PROFILES
    table = Table(title="内置站点模式库", box=box.ROUNDED)
    table.add_column("分类", style="cyan")
    table.add_column("典型算法", style="white")
    table.add_column("难度", style="yellow")
    table.add_column("策略", style="green")
    for p in KNOWN_PROFILES:
        table.add_row(p.category, p.typical_algorithm, p.difficulty, p.strategy)
    console.print(table)


@app.command()
def info() -> None:
    """显示系统配置和记忆库统计"""
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
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)

    # 记忆库统计
    try:
        mem_dir = settings.workspace / "memory"
        db_path = mem_dir / "axelo.db"
        if db_path.exists():
            from axelo.memory.db import MemoryDB
            db = MemoryDB(db_path)
            sessions_list = db.get_similar_sessions("")
            console.print(f"\n[dim]记忆库: {db_path} | 历史会话: {len(sessions_list)}条[/dim]")
    except Exception:
        pass


if __name__ == "__main__":
    app()
