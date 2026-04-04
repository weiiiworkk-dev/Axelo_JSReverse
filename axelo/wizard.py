from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

import structlog
from pydantic import ValidationError
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from axelo.models.run_config import RunConfig

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console()

_PROJECT_ROOT = Path(__file__).parent.parent
_STEP_TOTAL = 9

_BANNER = """
[bold cyan]    _              _         _  ____  ____                              [/bold cyan]
[bold cyan]   / \\  __  ___  | | ___   | |/ ___|  _ \\ _____   _____ _ __ ___  ___  [/bold cyan]
[bold cyan]  / _ \\ \\ \\/ / _ \\| |/ _ \\  | |\\___ \\| |_) / _ \\ \\ / / _ \\ '__/ __|/ _ \\ [/bold cyan]
[bold cyan] / ___ \\ >  <  __/| | (_) | | | ___) |  _ <  __/\\ V /  __/ |  \\__ \\  __/ [/bold cyan]
[bold cyan]/_/   \\_/_/\\_\\___|_|\\___/  |_||____/|_| \\_\\___| \\_/ \\___|_|  |___/\\___| [/bold cyan]
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
    ("interactive", "关键节点人工确认，适合第一次跑"),
    ("auto", "全自动执行，适合你已经知道自己要什么"),
    ("manual", "每一步都等待审批，控制权最高"),
]

_BUDGETS = [
    (1.0, "$1  轻量任务，适合先探测"),
    (3.0, "$3  标准预算，推荐默认"),
    (5.0, "$5  复杂站点，多层混淆更稳"),
    (10.0, "$10 深度分析，给极难站点留空间"),
    (None, "自定义金额"),
]

_ENDPOINT_OPTIONS = [
    ("known", "已知接口路径（手动输入）"),
    ("discover", "需要系统自动发现"),
    ("unknown", "完全不确定"),
]

_ANTIBOT_OPTIONS = [
    ("cloudflare", "Cloudflare（CF challenge / 5s 页面）"),
    ("datadome", "DataDome（行为分析型）"),
    ("akamai", "Akamai / PerimeterX"),
    ("custom", "自定义签名（非第三方平台）"),
    ("unknown", "不清楚，让系统判断"),
]

_LOGIN_OPTIONS = [
    (False, "无需登录（匿名接口）"),
    (True, "需要登录态（提供 Cookie）"),
    (None, "不确定"),
]

_OUTPUT_OPTIONS = [
    ("json_file", "JSON 文件（crawler_output.json）"),
    ("csv", "CSV 文件（crawler_output.csv）"),
    ("print", "打印到屏幕（直接输出）"),
    ("custom", "自定义（生成代码时说明）"),
]

_CRAWL_RATE_OPTIONS = [
    ("conservative", "保守：每次请求间隔 3 秒，低风险"),
    ("standard", "标准：每次请求间隔 1 秒"),
    ("aggressive", "激进：最快速度，不添加延迟"),
]


def _progress_bar(step: int) -> str:
    return f"[cyan][{'=' * step}{'.' * (_STEP_TOTAL - step)}][/cyan] [bold]{step}/{_STEP_TOTAL}[/bold]"


def _show_step(step: int, title: str, subtitle: str) -> None:
    body = Group(
        f"[bold white]{title}[/bold white]",
        f"[dim]{subtitle}[/dim]",
        _progress_bar(step),
    )
    console.print()
    console.print(Panel(body, border_style="cyan", padding=(0, 1)))


def _choose(options: list[str], default: int = 1) -> int:
    for index, option in enumerate(options, 1):
        marker = "[cyan bold]>[/cyan bold]" if index == default else " "
        console.print(f"  {marker} [cyan]{index}[/cyan]  {option}")
    console.print()

    while True:
        raw = input(f"  请输入序号 [默认 {default}]: ").strip()
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print(f"  [red]请输入 1 ~ {len(options)} 之间的数字。[/red]")


def _ensure_env() -> None:
    env_file = _PROJECT_ROOT / ".env"
    example_file = _PROJECT_ROOT / ".env.example"

    if not env_file.exists():
        if example_file.exists():
            shutil.copy(example_file, env_file)
            console.print(
                Panel(
                    "[yellow]已从 .env.example 自动创建 .env。[/yellow]\n"
                    f"请打开 [cyan]{env_file}[/cyan]\n"
                    "把 [bold]ANTHROPIC_API_KEY[/bold] 换成你的真实密钥后再运行。",
                    title="[bold yellow]首次配置[/bold yellow]",
                    border_style="yellow",
                )
            )
            sys.exit(0)
        console.print("[red]找不到 .env.example，请手动创建 .env。[/red]")
        sys.exit(1)

    content = env_file.read_text(encoding="utf-8")
    if "sk-ant-" not in content or "ANTHROPIC_API_KEY=sk-ant-..." in content:
        console.print(
            Panel(
                f"[yellow]检测到 .env 中还没有真实 API Key。[/yellow]\n"
                f"请打开 [cyan]{env_file}[/cyan] 完成配置后再运行。",
                title="[bold yellow]API Key 未配置[/bold yellow]",
                border_style="yellow",
            )
        )
        sys.exit(0)


def _target_url_note(url: str) -> str | None:
    parsed = urlsplit(url)
    normalized_path = parsed.path.rstrip("/")
    if parsed.fragment and normalized_path in {"", "/"}:
        return "当前 URL 带有 hash 片段，首页型 SPA 往往会抓到大量无关脚本；更具体的落地页通常更稳。"
    if normalized_path in {"", "/"} and not parsed.query:
        return "当前像是站点首页。若目标是商品或价格，建议直接输入商品详情页或搜索结果页。"
    return None


def _specificity_label(url: str, known_endpoint: str) -> str:
    note = _target_url_note(url)
    if known_endpoint:
        return "[green]高[/green]"
    if note:
        return "[yellow]低[/yellow]"
    return "[cyan]中[/cyan]"


def _runtime_label(url: str, mode: str, known_endpoint: str) -> str:
    if mode == "manual":
        return "手动推进，耗时取决于审批频率"
    if known_endpoint:
        return "约 2-5 分钟"
    if _target_url_note(url):
        return "约 4-8 分钟，且更容易抓到噪声"
    return "约 3-6 分钟"


def _risk_label(url: str, antibot_type: str, requires_login: bool | None) -> str:
    score = 0
    if _target_url_note(url):
        score += 2
    if antibot_type == "unknown":
        score += 1
    if requires_login is not False:
        score += 1
    if score >= 3:
        return "[yellow]偏高[/yellow]"
    if score == 2:
        return "[cyan]中等[/cyan]"
    return "[green]较低[/green]"


def _mode_label(mode: str) -> str:
    mapping = {
        "interactive": "interactive",
        "auto": "auto",
        "manual": "manual",
    }
    return mapping.get(mode, mode)


def _endpoint_label(known_endpoint: str) -> str:
    return known_endpoint or "需要系统自动发现"


def _antibot_label(antibot_type: str) -> str:
    mapping = {value: label for value, label in _ANTIBOT_OPTIONS}
    return mapping.get(antibot_type, antibot_type)


def _login_label(requires_login: bool | None) -> str:
    if requires_login is True:
        return "需要登录态（提供 Cookie）"
    if requires_login is False:
        return "无需登录（匿名接口）"
    return "不确定"


def _output_label(output_format: str) -> str:
    mapping = {value: label for value, label in _OUTPUT_OPTIONS}
    return mapping.get(output_format, output_format)


def _crawl_rate_label(crawl_rate: str) -> str:
    mapping = {value: label for value, label in _CRAWL_RATE_OPTIONS}
    return mapping.get(crawl_rate, crawl_rate)


def _launch_recommendations(
    url: str,
    goal: str,
    known_endpoint: str,
    requires_login: bool | None,
    mode: str,
    budget: float,
) -> list[str]:
    recommendations: list[str] = []
    url_note = _target_url_note(url)
    if url_note:
        recommendations.append(url_note)
    if not known_endpoint:
        recommendations.append("如果你已经知道接口片段，补一个路径关键词会显著加快定位。")
    if ("商品" in goal or "价格" in goal) and _target_url_note(url):
        recommendations.append("商品和价格任务优先用商品详情页或搜索结果页，命中率通常更高。")
    if requires_login is None:
        recommendations.append("登录状态未知时，系统会先按匿名接口尝试；失败后再升级复杂度。")
    if mode == "auto" and budget <= 1:
        recommendations.append("低预算 + auto 更适合探测，不适合一开始就冲复杂站点。")
    if not recommendations:
        recommendations.append("当前配置比较均衡，可以直接启动。")
    return recommendations[:4]


def _show_intro() -> None:
    console.print(Panel(_BANNER, border_style="cyan", padding=(0, 1)))
    console.print("[dim]Axelo JSReverse  |  AI 驱动的网页 JS 逆向系统[/dim]\n")
    console.print(
        Panel(
            Group(
                "[bold white]这次运行会做什么[/bold white]",
                "1. 爬目标页，发现 JS 和关键请求",
                "2. 选择更合适的 bundle 做去混淆和静态分析",
                "3. 再进入 AI 分析、代码生成和验证",
            ),
            title="[bold cyan]启动导览[/bold cyan]",
            border_style="cyan",
        )
    )


def _ask_url() -> str:
    _show_step(1, "目标网站 URL", "请输入完整网址，建议尽量直接给到更具体的落地页。")
    while True:
        raw = input("  URL: ").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            note = _target_url_note(raw)
            if note:
                console.print(f"  [yellow]提示：{note}[/yellow]")
            return raw
        console.print("  [red]URL 必须以 http:// 或 https:// 开头。[/red]")


def _ask_goal() -> str:
    _show_step(2, "爬取目标数据类型", "告诉系统你更想复现哪一类接口。")
    idx = _choose([label for label, _ in _GOALS], default=1)
    _, value = _GOALS[idx - 1]
    if value is None:
        custom = input("  自定义目标: ").strip()
        return custom or "逆向接口签名，生成完整爬虫脚本"
    return value


def _ask_endpoint() -> str:
    _show_step(3, "目标接口特征", "如果已经知道接口路径，后续定位会快很多。")
    idx = _choose([label for _, label in _ENDPOINT_OPTIONS], default=2)
    choice = _ENDPOINT_OPTIONS[idx - 1][0]
    if choice == "known":
        while True:
            endpoint = input("  请输入接口路径（如 /api/search）: ").strip()
            if endpoint:
                return endpoint
            console.print("  [red]接口路径不能为空。[/red]")
    return ""


def _ask_antibot() -> str:
    _show_step(4, "反爬虫防护类型", "不确定时让系统判断即可。")
    idx = _choose([label for _, label in _ANTIBOT_OPTIONS], default=5)
    return _ANTIBOT_OPTIONS[idx - 1][0]


def _ask_login() -> bool | None:
    _show_step(5, "是否需要登录", "登录态会影响执行层级和验证策略。")
    idx = _choose([label for _, label in _LOGIN_OPTIONS], default=3)
    return _LOGIN_OPTIONS[idx - 1][0]


def _ask_output_format() -> str:
    _show_step(6, "数据输出格式", "决定生成脚本默认把数据写到哪里。")
    idx = _choose([label for _, label in _OUTPUT_OPTIONS], default=1)
    return _OUTPUT_OPTIONS[idx - 1][0]


def _ask_crawl_rate() -> str:
    _show_step(7, "爬取频率偏好", "频率越高越快，但也更容易触发风控。")
    idx = _choose([label for _, label in _CRAWL_RATE_OPTIONS], default=2)
    return _CRAWL_RATE_OPTIONS[idx - 1][0]


def _ask_mode() -> str:
    _show_step(8, "运行模式", "第一次跑推荐 interactive，重复任务可以用 auto。")
    labels = [f"[green]{name}[/green]  -  {desc}" for name, desc in _MODES]
    idx = _choose(labels, default=1)
    return _MODES[idx - 1][0]


def _ask_budget() -> float:
    _show_step(9, "AI 费用预算上限", "预算越高，系统越敢走更重的分析路径。")
    idx = _choose([label for _, label in _BUDGETS], default=2)
    value, _ = _BUDGETS[idx - 1]
    if value is None:
        while True:
            raw = input("  请输入金额（USD，如 7.5）: ").strip()
            try:
                budget = float(raw)
                if budget > 0:
                    return budget
            except ValueError:
                pass
            console.print("  [red]请输入正数。[/red]")
    return value


def _show_summary(
    url: str,
    goal: str,
    known_endpoint: str,
    antibot_type: str,
    requires_login: bool | None,
    output_format: str,
    crawl_rate: str,
    mode: str,
    budget: float,
) -> None:
    config_table = Table(box=box.ROUNDED, show_header=False, border_style="cyan", padding=(0, 1))
    config_table.add_column("项目", style="dim", width=12)
    config_table.add_column("内容", style="white")
    config_table.add_row("目标 URL", f"[yellow]{url}[/yellow]")
    config_table.add_row("逆向目标", goal)
    config_table.add_row("接口线索", _endpoint_label(known_endpoint))
    config_table.add_row("反爬类型", _antibot_label(antibot_type))
    config_table.add_row("登录需求", _login_label(requires_login))
    config_table.add_row("输出格式", _output_label(output_format))
    config_table.add_row("爬取频率", _crawl_rate_label(crawl_rate))
    config_table.add_row("运行模式", f"[green]{_mode_label(mode)}[/green]")
    config_table.add_row("费用预算", f"[cyan]${budget:.1f}[/cyan]")

    recommendations = _launch_recommendations(
        url=url,
        goal=goal,
        known_endpoint=known_endpoint,
        requires_login=requires_login,
        mode=mode,
        budget=budget,
    )
    insight_lines = [
        f"目标精确度: {_specificity_label(url, known_endpoint)}",
        f"风险等级: {_risk_label(url, antibot_type, requires_login)}",
        f"预估耗时: {_runtime_label(url, mode, known_endpoint)}",
        "",
        "[bold white]启动建议[/bold white]",
        *[f"- {item}" for item in recommendations],
    ]
    insight_panel = Panel(
        "\n".join(insight_lines),
        title="[bold cyan]启动前画像[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    )

    console.print()
    console.print(Columns([config_table, insight_panel], equal=True, expand=True))


def main() -> None:
    _show_intro()
    _ensure_env()

    url = _ask_url()
    goal = _ask_goal()
    known_endpoint = _ask_endpoint()
    antibot_type = _ask_antibot()
    requires_login = _ask_login()
    output_format = _ask_output_format()
    crawl_rate = _ask_crawl_rate()
    mode = _ask_mode()
    budget = _ask_budget()

    _show_summary(
        url=url,
        goal=goal,
        known_endpoint=known_endpoint,
        antibot_type=antibot_type,
        requires_login=requires_login,
        output_format=output_format,
        crawl_rate=crawl_rate,
        mode=mode,
        budget=budget,
    )

    console.print()
    confirm = input("  确认以上信息并启动？[Y/n] ").strip().lower()
    if confirm in {"n", "no"}:
        console.print("[dim]已取消。[/dim]")
        return

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    from axelo.orchestrator.master import MasterOrchestrator

    try:
        run_cfg = RunConfig(
            url=url,
            goal=goal,
            mode_name=mode,
            budget_usd=budget,
            known_endpoint=known_endpoint,
            antibot_type=antibot_type,
            requires_login=requires_login,
            output_format=output_format,
            crawl_rate=crawl_rate,
        )
    except ValidationError as exc:
        console.print(f"[red]参数校验失败[/red]\n{exc}")
        return

    orchestrator = MasterOrchestrator()
    result = asyncio.run(orchestrator.run(**run_cfg.orchestrator_kwargs()))

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
        if result.report_path:
            console.print(f"  [dim]报告: {result.report_path}[/dim]")
    else:
        console.print(f"\n[bold red]✗ 未完成[/bold red]: {result.error or '未知错误'}")
        console.print(f"  续跑: [dim]axelo run {url} --resume --session {result.session_id}[/dim]")


if __name__ == "__main__":
    main()
