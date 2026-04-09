"""
Axelo Welcome Screen - 欢迎页
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align

from axelo.ui.logo import LOGO_COMPACT, get_logo
from axelo.ui.theme import ThemeColors


def show_welcome(console: Console) -> None:
    """显示欢迎界面"""
    
    # Logo
    logo_text = Text(LOGO_COMPACT)
    logo_text.stylize("primary")
    
    # 欢迎信息
    welcome = Text()
    welcome.append("👋 欢迎使用 ", style="primary_light")
    welcome.append("Axelo", style="primary bold")
    welcome.append("\n", style="text_primary")
    welcome.append("输入网站名称或 URL 开始自动逆向与爬取", style="text_secondary")
    
    # 示例
    examples = Text()
    examples.append("示例: ", style="text_muted")
    examples.append("jd.com", style="primary")
    examples.append("  ", style="text_primary")
    examples.append("淘宝", style="primary")
    examples.append("  ", style="text_primary")
    examples.append("amazon", style="primary")
    examples.append("  ", style="text_primary")
    examples.append("拼多多", style="primary")
    examples.append("  ", style="text_primary")
    examples.append("小红书", style="primary")
    examples.append("  ", style="text_primary")
    examples.append("抖音", style="primary")
    
    # 输入提示
    prompt = Text()
    prompt.append("➜ ", style="primary bold")
    prompt.append("_", style="primary blink")
    
    # 组合内容
    content = Text()
    content.append("\n")
    content.append(logo_text)
    content.append("\n\n")
    content.append(welcome)
    content.append("\n\n")
    content.append(examples)
    content.append("\n\n\n")
    content.append(prompt)
    
    # 渲染 Panel
    panel = Panel(
        Align.center(content),
        border_style="primary",
        padding=(1, 2),
    )
    
    console.print(panel)


def show_help(console: Console) -> None:
    """显示帮助信息"""
    
    table = Table(title=" 命令帮助 ", box=None, show_header=False)
    table.add_column("命令", style="primary", width=15)
    table.add_column("说明", style="text_primary")
    
    commands = [
        ("help", "显示帮助信息"),
        ("status", "显示系统状态"),
        ("history", "显示历史任务"),
        ("memory", "显示记忆库统计"),
        ("profile", "显示当前配置"),
        ("clear", "清屏"),
        ("quit", "退出程序"),
    ]
    
    for cmd, desc in commands:
        table.add_row(f"[primary]{cmd}[/]", desc)
    
    console.print(table)


def show_system_status(console: Console) -> None:
    """显示系统状态"""
    
    table = Table(title=" 系统状态 ", box=None)
    table.add_column("项目", style="primary", width=20)
    table.add_column("值", style="text_primary")
    
    # 示例数据
    status_items = [
        ("版本", "0.1.0"),
        ("运行模式", "交互模式"),
        ("预算", "$2.00"),
        ("已消耗", "$0.00"),
        ("历史任务", "48"),
        ("记忆库", "12 条"),
    ]
    
    for item, value in status_items:
        table.add_row(item, value)
    
    console.print(table)


def show_command_bar(console: Console) -> None:
    """显示底部命令栏"""
    
    commands = Text()
    commands.append("[help] ", style="primary_light")
    commands.append("帮助  ", style="text_muted")
    commands.append("[status] ", style="primary_light")
    commands.append("状态  ", style="text_muted")
    commands.append("[history] ", style="primary_light")
    commands.append("历史  ", style="text_muted")
    commands.append("[memory] ", style="primary_light")
    commands.append("记忆库  ", style="text_muted")
    commands.append("[clear] ", style="primary_light")
    commands.append("清屏", style="text_muted")
    
    panel = Panel(
        Align.center(commands),
        border_style="primary",
        padding=(0, 1),
    )
    
    console.print(panel)


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "show_welcome",
    "show_help",
    "show_system_status",
    "show_command_bar",
]