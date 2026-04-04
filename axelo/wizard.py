from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import structlog
from pydantic import ValidationError
from rich import box
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from axelo.config import settings
from axelo.models.run_config import RunConfig

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console()

_PROJECT_ROOT = Path(__file__).parent.parent
_STEP_TOTAL = 10

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
    ("auto", "全自动执行，适合目标很明确的重复任务"),
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

_PIPELINE_STAGE_ORDER = [
    ("planning", "任务规划"),
    ("s1_crawl", "页面爬取"),
    ("s2_fetch", "资源抓取"),
    ("s3_deobfuscate", "去混淆"),
    ("s4_static", "静态分析"),
    ("s5_dynamic", "动态分析"),
    ("s6_ai_analyze", "AI 分析"),
    ("s7_codegen", "代码生成"),
    ("s8_verify", "验证回放"),
    ("memory_write", "记忆写入"),
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
        return "当前 URL 带有 hash 片段，首页型 SPA 往往会抓到大量无关脚本，更具体的落地页通常更稳。"
    if normalized_path in {"", "/"} and not parsed.query:
        return "当前像是站点首页。若目标是商品、搜索或价格，建议直接输入商品页、搜索结果页或类目页。"
    return None


def _goal_requires_target_hint(goal: str) -> bool:
    normalized = goal.lower()
    keywords = (
        "商品",
        "价格",
        "搜索",
        "列表",
        "评论",
        "内容",
        "product",
        "price",
        "search",
        "list",
        "review",
        "content",
        "sku",
        "item",
    )
    return any(keyword in normalized for keyword in keywords)


def _target_hint_required(url: str, goal: str) -> bool:
    return _goal_requires_target_hint(goal) and _target_url_note(url) is not None


def _specificity_label(url: str, known_endpoint: str, target_hint: str) -> str:
    if known_endpoint and target_hint:
        return "[green]高[/green]"
    if known_endpoint or target_hint:
        return "[cyan]中[/cyan]"
    if _target_url_note(url):
        return "[yellow]低[/yellow]"
    return "[cyan]中[/cyan]"


def _runtime_label(url: str, goal: str, mode: str, known_endpoint: str, target_hint: str) -> str:
    if mode == "manual":
        return "手动推进，耗时取决于审批频率"
    if known_endpoint and target_hint:
        return "约 2-5 分钟"
    if _target_hint_required(url, goal) and not target_hint:
        return "约 4-8 分钟，且容易抓到偏题请求"
    if _target_url_note(url):
        return "约 4-8 分钟，且更容易抓到噪声"
    return "约 3-6 分钟"


def _risk_label(url: str, antibot_type: str, requires_login: bool | None, target_hint: str) -> str:
    score = 0
    if _target_url_note(url):
        score += 2
    if not target_hint:
        score += 1
    if antibot_type == "unknown":
        score += 1
    if requires_login is not False:
        score += 1
    if score >= 4:
        return "[yellow]偏高[/yellow]"
    if score >= 2:
        return "[cyan]中等[/cyan]"
    return "[green]较低[/green]"


def _mode_label(mode: str) -> str:
    return mode


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


def _target_hint_label(target_hint: str) -> str:
    return target_hint or "[red]未指定[/red]"


def _launch_recommendations(
    url: str,
    goal: str,
    target_hint: str,
    known_endpoint: str,
    requires_login: bool | None,
    mode: str,
    budget: float,
) -> list[str]:
    recommendations: list[str] = []
    url_note = _target_url_note(url)
    if url_note:
        recommendations.append(url_note)
    if not target_hint:
        recommendations.append("目标对象未指定。建议补商品 URL、搜索词、SKU 或类目锚点，避免系统抓到偏题接口。")
    if not known_endpoint:
        recommendations.append("如果你已经知道接口片段，补一个路径关键词会显著加快定位。")
    if ("商品" in goal or "价格" in goal) and _target_url_note(url):
        recommendations.append("商品和价格任务优先用商品详情页、搜索结果页或类目页，命中率通常更高。")
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
                "1. 抓目标页，发现 JS 和关键请求",
                "2. 选择更合适的 bundle 做去混淆和静态分析",
                "3. 只有在自动化链路不够时，才进入 AI 分析、代码生成和验证",
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


def _ask_target_hint(url: str, goal: str) -> str:
    _show_step(3, "目标对象定位", "可填写商品 URL、搜索词、SKU、店铺名或类目锚点，避免系统自己瞎猜。")
    required = _target_hint_required(url, goal)
    if required:
        console.print("  [yellow]当前是泛入口页，这一步建议不要留空。[/yellow]")
    while True:
        raw = input("  目标对象（可填 iPhone 15 / 商品链接 / SKU）: ").strip()
        if raw:
            return raw
        if not required:
            console.print("  [dim]未填写目标对象，系统会按泛目标运行，结果可能偏题。[/dim]")
            return ""
        console.print("  [red]当前 URL 过于泛，请至少补一个目标对象锚点。[/red]")


def _ask_endpoint() -> str:
    _show_step(4, "目标接口特征", "如果已经知道接口路径，后续定位会快很多。")
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
    _show_step(5, "反爬虫防护类型", "不确定时让系统判断即可。")
    idx = _choose([label for _, label in _ANTIBOT_OPTIONS], default=5)
    return _ANTIBOT_OPTIONS[idx - 1][0]


def _ask_login() -> bool | None:
    _show_step(6, "是否需要登录", "登录态会影响执行层级和验证策略。")
    idx = _choose([label for _, label in _LOGIN_OPTIONS], default=3)
    return _LOGIN_OPTIONS[idx - 1][0]


def _ask_output_format() -> str:
    _show_step(7, "数据输出格式", "决定生成脚本默认把数据写到哪里。")
    idx = _choose([label for _, label in _OUTPUT_OPTIONS], default=1)
    return _OUTPUT_OPTIONS[idx - 1][0]


def _ask_crawl_rate() -> str:
    _show_step(8, "爬取频率偏好", "频率越高越快，但也更容易触发风控。")
    idx = _choose([label for _, label in _CRAWL_RATE_OPTIONS], default=2)
    return _CRAWL_RATE_OPTIONS[idx - 1][0]


def _ask_mode() -> str:
    _show_step(9, "运行模式", "目标不够具体时，优先用 interactive；目标明确后再切 auto。")
    labels = [f"[green]{name}[/green]  -  {desc}" for name, desc in _MODES]
    idx = _choose(labels, default=1)
    return _MODES[idx - 1][0]


def _ask_budget() -> float:
    _show_step(10, "AI 费用预算上限", "预算越高，系统越敢走更重的 AI 分析路径。")
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
    target_hint: str,
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
    config_table.add_row("目标对象", _target_hint_label(target_hint))
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
        target_hint=target_hint,
        known_endpoint=known_endpoint,
        requires_login=requires_login,
        mode=mode,
        budget=budget,
    )
    insight_lines = [
        f"目标精确度: {_specificity_label(url, known_endpoint, target_hint)}",
        f"风险等级: {_risk_label(url, antibot_type, requires_login, target_hint)}",
        f"预估耗时: {_runtime_label(url, goal, mode, known_endpoint, target_hint)}",
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


def _configure_wizard_logging(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", buffering=1)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.WriteLoggerFactory(file=log_file),
        cache_logger_on_first_use=True,
    )
    return log_file


def _safe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _status_style(status: str) -> str:
    mapping = {
        "completed": "[green]completed[/green]",
        "running": "[cyan]running[/cyan]",
        "pending": "[dim]pending[/dim]",
        "failed": "[red]failed[/red]",
        "manual_review": "[yellow]manual[/yellow]",
        "started": "[cyan]started[/cyan]",
    }
    return mapping.get(status, status or "[dim]pending[/dim]")


def _last_checkpoint_by_stage(trace_data: dict) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for checkpoint in trace_data.get("checkpoints", []):
        stage_name = checkpoint.get("stage_name", "")
        if stage_name:
            latest[stage_name] = checkpoint
    return latest


def _render_runtime_dashboard(
    *,
    session_id: str,
    url: str,
    target_hint: str,
    started_at: float,
    trace_data: dict,
    state_data: dict,
    log_path: Path,
):
    elapsed_seconds = int(max(0.0, time.monotonic() - started_at))
    last_checkpoint = (trace_data.get("checkpoints") or [{}])[-1]
    current_stage = last_checkpoint.get("stage_name") or "waiting"
    current_status = last_checkpoint.get("status") or state_data.get("workflow_status", "running")

    header = Table(box=box.ROUNDED, show_header=False, border_style="cyan", padding=(0, 1))
    header.add_column("键", style="dim", width=12)
    header.add_column("值", style="white")
    header.add_row("会话", session_id)
    header.add_row("当前阶段", current_stage)
    header.add_row("状态", _status_style(current_status))
    header.add_row("已运行", f"{elapsed_seconds}s")
    header.add_row("目标对象", target_hint or "[red]未指定[/red]")
    header.add_row("日志文件", str(log_path))

    stage_table = Table(box=box.ROUNDED, border_style="cyan", expand=True)
    stage_table.add_column("阶段", style="white", width=14)
    stage_table.add_column("状态", style="white", width=12)
    stage_table.add_column("摘要", style="dim")

    checkpoints = _last_checkpoint_by_stage(trace_data)
    for stage_name, label in _PIPELINE_STAGE_ORDER:
        checkpoint = checkpoints.get(stage_name, {})
        summary = checkpoint.get("summary", "")
        stage_table.add_row(label, _status_style(checkpoint.get("status", "pending")), _truncate(summary, 88))

    recent_events = Table(box=box.ROUNDED, border_style="cyan", expand=True)
    recent_events.add_column("最近事件", style="white")
    recent_events.add_column("摘要", style="dim")
    for checkpoint in (trace_data.get("checkpoints") or [])[-4:]:
        recent_events.add_row(
            f"{checkpoint.get('stage_name', '-')}: {checkpoint.get('status', '-')}",
            _truncate(checkpoint.get("summary", ""), 72),
        )
    if recent_events.row_count == 0:
        recent_events.add_row("waiting", "正在等待首个阶段写入 trace")

    body = Group(
        Panel(
            header,
            title=f"[bold cyan]运行中[/bold cyan]  {url}",
            border_style="cyan",
        ),
        Columns(
            [
                Panel(stage_table, title="[bold cyan]阶段进度[/bold cyan]", border_style="cyan"),
                Panel(recent_events, title="[bold cyan]最近事件[/bold cyan]", border_style="cyan"),
            ],
            equal=True,
            expand=True,
        ),
    )
    return body


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _load_verify_report_text(session_dir: Path) -> str:
    verify_path = session_dir / "output" / "verify_report.txt"
    if not verify_path.exists():
        return ""
    try:
        return verify_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _failure_insight(result, session_dir: Path) -> dict[str, object]:
    trace_data = _safe_load_json(session_dir / "workflow_trace.json")
    run_report = _safe_load_json(session_dir / "run_report.json")
    verify_text = _load_verify_report_text(session_dir)
    checkpoints = trace_data.get("checkpoints") or []
    failed_checkpoints = [checkpoint for checkpoint in checkpoints if checkpoint.get("status") == "failed"]
    chosen_checkpoint = failed_checkpoints[-1] if failed_checkpoints else (checkpoints[-1] if checkpoints else {})
    latest_stage = chosen_checkpoint.get("stage_name", "unknown")
    latest_summary = chosen_checkpoint.get("summary", "")

    verification_notes = (
        run_report.get("result", {}).get("verification_notes", "")
        if isinstance(run_report.get("result"), dict)
        else ""
    )
    signal_text = "\n".join(filter(None, [result.error or "", latest_summary, verification_notes, verify_text])).lower()

    cause = "流程已经结束，但需要人工复查当前产物。"
    actions = [
        "优先检查 session 目录里的 run_report.json、workflow_trace.json 和 verify_report.txt。",
    ]

    if "getaddrinfo failed" in signal_text:
        cause = "生成代码中的 API 主机不可解析，通常是把站点域名或移动端 API host 猜错了。"
        actions = [
            "优先检查观测到的 target requests 是否已经被正确锚定到生成代码常量。",
            "如果入口页过泛，请改用商品页、搜索页或补充更明确的目标对象提示。",
        ]
    elif "budget exhausted" in signal_text:
        cause = "预算在进入 AI 分析前就耗尽了，当前任务没有拿到足够上下文。"
        actions = [
            "提高预算，或者先补 known endpoint / target hint，缩短自动化链路。",
            "优先复用记忆命中和 bundle 缓存，避免重复做昂贵阶段。",
        ]
    elif "manual review required" in signal_text:
        cause = "当前目标被判定为高风险或高复杂度，需要人工介入。"
        actions = [
            "先缩小目标范围，再重跑一轮自动化流程。",
            "必要时把 auto 切回 interactive，逐步确认目标请求。",
        ]
    elif "node 调用超时" in signal_text or "timeout" in signal_text:
        cause = "本地 JS 分析阶段超时，某个 bundle 太大或噪声太多。"
        actions = [
            "换更具体的目标页，减少首页型 bundle 噪声。",
            "补已知接口路径或目标对象提示，让候选 bundle 收敛得更快。",
        ]
    elif "403" in signal_text:
        cause = "签名、Cookie 或行为校验没有通过，服务端拒绝了请求。"
        actions = [
            "检查是否需要登录态、CSRF Token 或特定请求头。",
            "确认验证阶段使用的 host、path、参数顺序与观测请求一致。",
        ]
    elif "401" in signal_text:
        cause = "当前产物缺少有效登录态或认证参数。"
        actions = [
            "补浏览器登录态 / Cookie，再做验证回放。",
            "确认生成代码没有丢失依赖登录态的 header 或 token。",
        ]
    elif "no_api_calls_captured" in signal_text or ("captured 0" in signal_text and latest_stage == "s1_crawl"):
        cause = "浏览器阶段没有抓到足够 API 请求，通常是入口页过泛或动作流不对。"
        actions = [
            "换成更具体的目标页，或者明确提供商品 URL / 搜索词 / SKU。",
            "优先用 interactive 模式确认目标请求，再切到 auto。",
        ]
    elif "crawl() execution failed: none" in signal_text:
        cause = "生成代码已经运行，但没有把回放请求头暴露给验证器，当前更像是代码契约不完整而不是站点完全失败。"
        actions = [
            "检查生成 crawler 是否在主请求前设置了 self._last_headers。",
            "如果是 bridge 模式，再确认签名请求和业务请求共用的是同一份 header 集合。",
        ]
    elif result.completed and not result.verified:
        cause = "主流程跑完了，但验证回放没有通过，当前代码还不够稳定。"
        actions = [
            "查看 verify_report.txt，确认失败是在 DNS、鉴权、签名还是数据质量环节。",
            "如果是泛入口页导致的偏题请求，补目标对象提示后重跑通常会更稳。",
        ]

    return {
        "title": "验证未通过摘要" if result.completed else "失败摘要",
        "stage": latest_stage,
        "summary": latest_summary or (result.error or "未提供摘要"),
        "cause": cause,
        "actions": actions,
    }


def _render_failure_summary(result, session_dir: Path):
    insight = _failure_insight(result, session_dir)
    lines = [
        f"阶段: [cyan]{insight['stage']}[/cyan]",
        f"摘要: {insight['summary']}",
        "",
        f"[bold white]判断[/bold white]  {insight['cause']}",
        "",
        "[bold white]建议动作[/bold white]",
        *[f"- {item}" for item in insight["actions"]],
    ]
    return Panel(
        "\n".join(lines),
        title=f"[bold yellow]{insight['title']}[/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
    )


def _run_with_dashboard(orchestrator, run_kwargs: dict, session_id: str, url: str, target_hint: str, log_path: Path):
    session_dir = settings.session_dir(session_id)
    state_path = session_dir / "state.json"
    trace_path = session_dir / "workflow_trace.json"
    started_at = time.monotonic()

    def _invoke():
        return asyncio.run(orchestrator.run(**run_kwargs))

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke)
        with Live(
            _render_runtime_dashboard(
                session_id=session_id,
                url=url,
                target_hint=target_hint,
                started_at=started_at,
                trace_data={},
                state_data={},
                log_path=log_path,
            ),
            console=console,
            refresh_per_second=4,
            transient=True,
        ) as live:
            while not future.done():
                live.update(
                    _render_runtime_dashboard(
                        session_id=session_id,
                        url=url,
                        target_hint=target_hint,
                        started_at=started_at,
                        trace_data=_safe_load_json(trace_path),
                        state_data=_safe_load_json(state_path),
                        log_path=log_path,
                    )
                )
                time.sleep(0.4)

            live.update(
                _render_runtime_dashboard(
                    session_id=session_id,
                    url=url,
                    target_hint=target_hint,
                    started_at=started_at,
                    trace_data=_safe_load_json(trace_path),
                    state_data=_safe_load_json(state_path),
                    log_path=log_path,
                )
            )
        return future.result()


def main() -> None:
    _show_intro()
    _ensure_env()

    url = _ask_url()
    goal = _ask_goal()
    target_hint = _ask_target_hint(url, goal)
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
        target_hint=target_hint,
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

    try:
        run_cfg = RunConfig(
            url=url,
            goal=goal,
            target_hint=target_hint,
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

    from axelo.orchestrator.master import MasterOrchestrator

    session_id = str(uuid.uuid4())[:8]
    session_dir = settings.session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "wizard.log"
    log_file = _configure_wizard_logging(log_path)

    console.print()
    console.print(
        Panel(
            f"[white]会话:[/white] [cyan]{session_id}[/cyan]\n"
            f"[white]目标对象:[/white] {target_hint or '未指定'}\n"
            f"[white]日志:[/white] {log_path}",
            title="[bold cyan]已启动[/bold cyan]",
            border_style="cyan",
        )
    )

    orchestrator = MasterOrchestrator()
    run_kwargs = run_cfg.orchestrator_kwargs()
    run_kwargs["session_id"] = session_id

    try:
        result = _run_with_dashboard(orchestrator, run_kwargs, session_id, url, target_hint, log_path)
    finally:
        log_file.close()

    if result.completed and result.verified:
        console.print(f"\n[bold green]✓ 逆向完成[/bold green]  会话: [cyan]{result.session_id}[/cyan]")
    elif result.completed:
        console.print(f"\n[bold yellow]! 流程完成，但验证未通过[/bold yellow]  会话: [cyan]{result.session_id}[/cyan]")
        console.print(_render_failure_summary(result, session_dir))
    else:
        console.print(f"\n[bold red]✗ 未完成[/bold red]  会话: [cyan]{result.session_id}[/cyan]")
        console.print(_render_failure_summary(result, session_dir))

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
    console.print(f"  [dim]日志: {log_path}[/dim]")


if __name__ == "__main__":
    main()
