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

# Lazy import to avoid breaking when modules don't exist
def _get_run_config():
    from axelo.models.run_config import RunConfig
    return RunConfig

def _get_session_store():
    from axelo.storage.session_store import SessionStore
    return SessionStore

def _get_patterns():
    from axelo.patterns.common import KNOWN_PROFILES
    return KNOWN_PROFILES

def _get_memory_db():
    from axelo.memory.db import MemoryDB
    return MemoryDB

def _get_profiles():
    from axelo.browser.profiles import PROFILES
    return PROFILES

def _setup_logging(log_level: str) -> None:
    import logging

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
    )


# Windows UTF-8 support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="axelo",
    help="AI 驱动的网页 JS 逆向系统",
    no_args_is_help=False,  # 禁用默认帮助，改为启动 chat
)
console = Console()


# 默认命令 - 不带参数时启动 chat
@app.callback(invoke_without_command=True)
def default_command(ctx: typer.Context):
    """默认启动 AI 对话界面"""
    if ctx.invoked_subcommand is None:
        # 没有子命令时，启动 chat
        import asyncio
        from axelo.chat.cli import AxeloChatCLI
        
        _setup_logging("info")
        asyncio.run(AxeloChatCLI().start())

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
        help="运行模式: interactive/full_auto/full_manual",
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
    
    RunConfig = _get_run_config()
    PROFILES = _get_profiles()

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

    console.print("\n[dim]使用新版 AI 对话式架构...[/dim]")
    from axelo.chat.cli import AxeloChatCLI

    # Run the chat CLI (blocking)
    cli = AxeloChatCLI()
    asyncio.run(cli._run_non_interactive(url, goal))


@app.command()
def sessions() -> None:
    """列出所有历史会话。"""
    SessionStore = _get_session_store()
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
    KNOWN_PROFILES = _get_patterns()

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
        ("API Key", "[green]已配置[/green]" if settings.deepseek_api_key else "[red]未配置[/red]"),
    ]
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)

    try:
        MemoryDB = _get_memory_db()
        mem_dir = settings.workspace / "memory"
        db_path = mem_dir / "axelo.db"
        if db_path.exists():
            db = MemoryDB(db_path)
            sessions_list = db.get_similar_sessions("")
            console.print(f"\n[dim]记忆库: {db_path} | 历史会话: {len(sessions_list)} 条[/dim]")
    except Exception:
        pass

@app.command()
def chat(
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动对话式 AI 逆向界面"""
    _setup_logging(log_level)
    
    from axelo.chat.cli import AxeloChatCLI
    
    asyncio.run(AxeloChatCLI().start())


@app.command()
def tools() -> None:
    """列出所有可用的 MCP Tools"""
    # Import tools to register them
    from axelo import tools as tools_module
    from axelo.tools.base import get_registry
    
    registry = get_registry()
    tools = registry.list_tools()
    
    if not tools:
        console.print("[yellow]暂无已注册的 Tools[/yellow]")
        console.print("[dim]提示: 需要导入 axelo.tools 模块来注册 Tools[/dim]")
        return
    
    table = Table(title="可用 MCP Tools", box=box.ROUNDED)
    table.add_column("Tool Name", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Description", style="white")
    
    for name in sorted(tools):
        tool = registry.get(name)
        if tool:
            table.add_row(name, tool.schema.category, tool.description)
    
    console.print(table)

if __name__ == "__main__":
    app()
