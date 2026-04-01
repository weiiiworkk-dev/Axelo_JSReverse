from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import structlog
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Windows CMD UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console()

# Project root: axelo/wizard.py → parent.parent = project root
_PROJECT_ROOT = Path(__file__).parent.parent

_BANNER = """
[bold cyan]    _              _         _  ____  ____                              [/bold cyan]
[bold cyan]   / \\  __  ___  | | ___   | |/ ___|  _ \\ _____   _____ _ __ ___  ___ [/bold cyan]
[bold cyan]  / _ \\ \\ \\/ / _ \\| |/ _ \\  | |\\___ \\| |_) / _ \\ \\ / / _ \\ '__/ __|/ _ \\[/bold cyan]
[bold cyan] / ___ \\ >  <  __/| | (_) | | | ___) |  _ <  __/\\ V /  __/ |  \\__ \\  __/[/bold cyan]
[bold cyan]/_/   \\_/_/\\_\\___|_|\\___/  |_||____/|_| \\_\\___| \\_/ \\___|_|  |___/\\___|[/bold cyan]
"""

_GOALS = [
    ("爬取搜索结果数据", "逆向搜索接口签名，生成可直接运行的搜索结果爬虫"),
    ("爬取视频 / 内容列表", "逆向内容接口签名，生成视频或内容列表爬虫"),
    ("爬取商品 / 价格数据", "逆向电商接口签名，生成商品详情或价格爬虫"),
    ("爬取评论 / 社交数据", "逆向评论接口签名，生成评论或帖子爬虫"),
    ("爬取用户 / 账号数据", "逆向用户接口签名，生成用户信息爬虫"),
    ("自定义（手动输入）", None),
]

_MODES = [
    ("interactive", "关键节点人工确认  [dim]推荐新用户[/dim]"),
    ("auto",        "全自动，无需干预  [dim]适合重复任务[/dim]"),
    ("manual",      "每步等待手动审批  [dim]最高控制权[/dim]"),
]

_BUDGETS = [
    (1.0,  "$ 1   轻量任务（简单签名）"),
    (3.0,  "$ 3   标准  [dim]推荐[/dim]"),
    (5.0,  "$ 5   复杂站点（多层混淆）"),
    (10.0, "$10   深度分析（极难站点）"),
    (None, "自定义金额"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _choose(title: str, options: list[str], default: int = 1) -> int:
    """Display a numbered menu and return the 1-based index chosen."""
    console.print(f"\n[bold white]{title}[/bold white]")
    for i, opt in enumerate(options, 1):
        marker = "[cyan bold]>[/cyan bold]" if i == default else " "
        console.print(f"  {marker} [cyan]{i}[/cyan]  {opt}")
    console.print()
    while True:
        raw = input(f"  请输入序号 [默认 {default}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print(f"  [red]请输入 1 ~ {len(options)} 之间的数字。[/red]")


def _ensure_env() -> None:
    """Copy .env.example → .env if .env is missing; warn if API key unset."""
    env_file = _PROJECT_ROOT / ".env"
    example_file = _PROJECT_ROOT / ".env.example"

    if not env_file.exists():
        if example_file.exists():
            shutil.copy(example_file, env_file)
            console.print(
                Panel(
                    "[yellow]已自动从 .env.example 创建 .env 文件。[/yellow]\n"
                    f"请用文本编辑器打开 [cyan]{env_file}[/cyan]\n"
                    "将 [bold]ANTHROPIC_API_KEY[/bold] 替换为你的真实 API Key，然后重新运行。",
                    title="[bold yellow]首次配置[/bold yellow]",
                    border_style="yellow",
                )
            )
            sys.exit(0)
        else:
            console.print("[red]找不到 .env.example，请手动创建 .env 文件。[/red]")
            sys.exit(1)

    # .env exists — check API key
    content = env_file.read_text(encoding="utf-8")
    if "sk-ant-" not in content or "ANTHROPIC_API_KEY=sk-ant-..." in content:
        console.print(
            Panel(
                f"[yellow]检测到 .env 中 ANTHROPIC_API_KEY 尚未配置。[/yellow]\n"
                f"请打开 [cyan]{env_file}[/cyan]，填入真实的 API Key 后重新运行。",
                title="[bold yellow]警告：API Key 未配置[/bold yellow]",
                border_style="yellow",
            )
        )
        sys.exit(0)


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def _ask_url() -> str:
    console.print("\n[bold white][步骤 1/4]  目标网站 URL[/bold white]")
    console.print("  [dim]请输入你想要逆向分析的完整网址（需包含 http:// 或 https://）[/dim]")
    while True:
        raw = input("  URL: ").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        console.print("  [red]URL 必须以 http:// 或 https:// 开头，请重新输入。[/red]")


def _ask_goal() -> str:
    labels = [label for label, _ in _GOALS]
    idx = _choose("[步骤 2/4]  爬取目标", labels, default=1)
    label, value = _GOALS[idx - 1]
    if value is None:
        console.print("  [dim]请输入自定义爬取目标描述：[/dim]")
        custom = input("  目标: ").strip()
        return custom or "逆向接口签名，生成完整爬虫脚本"
    return value


def _ask_mode() -> str:
    labels = [f"[green]{name}[/green]  —  {desc}" for name, desc in _MODES]
    idx = _choose("[步骤 3/4]  运行模式", labels, default=1)
    return _MODES[idx - 1][0]


def _ask_budget() -> float:
    labels = [desc for _, desc in _BUDGETS]
    idx = _choose("[步骤 4/4]  AI 费用预算上限", labels, default=2)
    value, _ = _BUDGETS[idx - 1]
    if value is None:
        while True:
            raw = input("  请输入金额（USD，如 7.5）: ").strip()
            try:
                v = float(raw)
                if v > 0:
                    return v
            except ValueError:
                pass
            console.print("  [red]请输入正数。[/red]")
    return value


def _show_summary(url: str, goal: str, mode: str, budget: float) -> None:
    table = Table(box=box.ROUNDED, show_header=False, border_style="cyan", padding=(0, 1))
    table.add_column("项目", style="dim", width=12)
    table.add_column("内容", style="white")
    table.add_row("目标 URL", f"[yellow]{url}[/yellow]")
    table.add_row("逆向目标", goal)
    table.add_row("运行模式", f"[green]{mode}[/green]")
    table.add_row("费用预算", f"[cyan]${budget}[/cyan]")
    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    console.print(Panel(_BANNER, border_style="cyan", padding=(0, 1)))
    console.print("[dim]  Axelo JSReverse  ——  AI 驱动的网页 JS 逆向系统[/dim]\n")

    _ensure_env()

    url = _ask_url()
    goal = _ask_goal()
    mode = _ask_mode()
    budget = _ask_budget()

    _show_summary(url, goal, mode, budget)

    console.print()
    confirm = input("  确认以上信息并启动？[Y/n] ").strip().lower()
    if confirm in ("n", "no"):
        console.print("[dim]已取消。[/dim]")
        return

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(__import__("logging").INFO)
    )

    from axelo.orchestrator.master import MasterOrchestrator

    orchestrator = MasterOrchestrator()
    result = asyncio.run(
        orchestrator.run(
            url=url,
            goal=goal,
            mode_name=mode,
            budget_usd=budget,
        )
    )

    if result.completed:
        console.print(f"\n[bold green]✓ 逆向完成[/bold green]  会话: [cyan]{result.session_id}[/cyan]")
        if result.difficulty:
            console.print(
                f"  难度: [yellow]{result.difficulty.level}[/yellow]  "
                f"验证: {'[green]通过[/green]' if result.verified else '[red]未通过[/red]'}"
            )
        if result.output_dir:
            console.print(f"  输出目录: [cyan]{result.output_dir}[/cyan]")
        if result.cost:
            console.print(f"  [dim]{result.cost.summary()}[/dim]")
    else:
        console.print(f"\n[bold red]✗ 未完成[/bold red]: {result.error or '未知错误'}")
        console.print(
            f"  续跑: [dim]axelo run {url} --resume --session {result.session_id}[/dim]"
        )
