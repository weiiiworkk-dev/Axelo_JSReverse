"""
Axelo UI Components - UI 组件库
"""

from dataclasses import dataclass
from typing import List, Optional

from rich.console import Console, ConsoleOptions, RenderResult
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.box import Box, ROUNDED, DOUBLE

from axelo.ui.theme import ThemeColors


# ═══════════════════════════════════════════════════════════════════════════════
# 进度条组件
# ═══════════════════════════════════════════════════════════════════════════════

def create_progress_bar() -> Progress:
    """创建自定义进度条"""
    return Progress(
        SpinnerColumn(spinner_name="dot", style="primary"),
        TextColumn("[progress.description]{task.description}", style="primary"),
        BarColumn(bar_width=None, complete_style="primary", finished_style="success"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%", style="primary_light"),
        console=Console(),
        expand=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 状态显示组件
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StatusItem:
    """状态项"""
    label: str
    status: str  # "success", "pending", "error", "info"
    detail: str = ""
    
    @property
    def icon(self) -> str:
        icons = {
            "success": "✓",
            "pending": "◐",
            "error": "✗",
            "info": "ℹ",
            "warning": "⚠",
        }
        return icons.get(self.status, "○")
    
    @property
    def style(self) -> str:
        styles = {
            "success": "success",
            "pending": "primary_light",
            "error": "error",
            "info": "info",
            "warning": "warning",
        }
        return styles.get(self.status, "primary")


def render_status_panel(title: str, items: List[StatusItem]) -> Panel:
    """渲染状态面板"""
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("icon", width=3)
    table.add_column("label", width=30)
    table.add_column("status", width=10)
    table.add_column("detail")
    
    for item in items:
        table.add_row(
            item.icon,
            item.label,
            Text(item.status.upper(), style=item.style),
            item.detail,
        )
    
    return Panel(
        table,
        title=f" {title} ",
        border_style="primary",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API 列表组件
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class APICandidateItem:
    """API 候选项"""
    index: int
    url: str
    method: str
    protection: str  # 保护信号
    confidence: float
    recommended: bool = False


def render_api_list(candidates: List[APICandidateItem]) -> Panel:
    """渲染 API 列表"""
    table = Table(box=None, show_header=True, padding=(0, 1))
    table.add_column("#", width=4, style="primary_light")
    table.add_column("Method", width=8, style="primary")
    table.add_column("URL", style="text_primary")
    table.add_column("保护", width=25, style="primary_light")
    table.add_column("置信度", width=10, justify="right")
    
    for item in candidates:
        method_style = "success" if item.method == "GET" else "warning"
        conf_str = f"{item.confidence * 100:.0f}%"
        
        # 置信度颜色
        if item.confidence >= 0.9:
            conf_style = "success bold"
        elif item.confidence >= 0.7:
            conf_style = "primary bold"
        else:
            conf_style = "warning"
        
        # 推荐标记
        prefix = "⭐ " if item.recommended else "   "
        
        table.add_row(
            f"{prefix}{item.index}",
            Text(item.method, style=method_style),
            item.url[:60] + "..." if len(item.url) > 60 else item.url,
            item.protection[:22] + "..." if len(item.protection) > 22 else item.protection,
            Text(conf_str, style=conf_style),
        )
    
    return Panel(
        table,
        title=" 发现 API ",
        border_style="primary",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 阶段进度组件
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StageProgress:
    """阶段进度"""
    name: str
    progress: float  # 0.0 - 1.0
    status: str = "running"  # "running", "completed", "pending", "error"


def render_stage_progress(stages: List[StageProgress]) -> Panel:
    """渲染阶段进度条"""
    lines = []
    
    for stage in stages:
        # 进度条
        bar_width = 30
        filled = int(bar_width * stage.progress)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # 状态图标
        icons = {
            "running": "▷",
            "completed": "✓",
            "pending": "○",
            "error": "✗",
        }
        icon = icons.get(stage.status, "○")
        
        # 颜色
        colors = {
            "running": "primary",
            "completed": "success",
            "pending": "text_muted",
            "error": "error",
        }
        color = colors.get(stage.status, "primary")
        
        lines.append(f" [{icon}] {stage.name:<12} [{color}]{bar}[/{color}]  {stage.progress * 100:>3.0f}%")
    
    content = Text("\n".join(lines))
    
    return Panel(
        content,
        title=" 逆向阶段 ",
        border_style="primary",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 日志显示组件
# ═══════════════════════════════════════════════════════════════════════════════

def render_log_panel(logs: List[str], max_lines: int = 10) -> Panel:
    """渲染日志面板"""
    # 只显示最近 max_lines 行
    display_logs = logs[-max_lines:] if len(logs) > max_lines else logs
    
    lines = []
    for log in display_logs:
        # 解析日志时间戳和内容
        if "]" in log:
            parts = log.split("]", 1)
            timestamp = parts[0] + "]"
            content = parts[1] if len(parts) > 1 else ""
            
            # 时间戳用弱化色
            lines.append(f"[text_muted]{timestamp}[/] {content}")
        else:
            lines.append(log)
    
    content = Text("\n".join(lines))
    
    return Panel(
        content,
        title=" 执行日志 ",
        border_style="primary",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 预算显示组件
# ═══════════════════════════════════════════════════════════════════════════════

def render_budget_display(used: float, total: float) -> Panel:
    """渲染预算显示"""
    percentage = (used / total) * 100 if total > 0 else 0
    
    bar_width = 20
    filled = int(bar_width * (used / total)) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    
    # 颜色
    if percentage >= 90:
        color = "error"
    elif percentage >= 70:
        color = "warning"
    else:
        color = "primary"
    
    content = Text(f" [{color}]{bar}[/{color}]  [bold]${used:.2f}[/] / ${total:.2f}")
    
    return Panel(
        content,
        title=" 预算消耗 ",
        border_style="primary",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 输出文件列表组件
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OutputFile:
    """输出文件"""
    name: str
    size: str
    status: str = "success"  # "success", "error"


def render_output_files(files: List[OutputFile]) -> Panel:
    """渲染输出文件列表"""
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("status", width=3)
    table.add_column("name", style="primary")
    table.add_column("size", style="text_muted", justify="right")
    
    for file in files:
        icon = "✅" if file.status == "success" else "❌"
        style = "success" if file.status == "success" else "error"
        
        table.add_row(
            Text(icon, style=style),
            file.name,
            file.size,
        )
    
    return Panel(
        table,
        title=" 输出文件 ",
        border_style="success",
        box=ROUNDED,
        padding=(1, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 命令栏组件
# ═══════════════════════════════════════════════════════════════════════════════

def render_command_bar(commands: List[str]) -> Panel:
    """渲染命令栏"""
    content = Text("  ".join(commands), style="primary_light")
    
    return Panel(
        Align.center(content),
        border_style="primary",
        box=Box.DOUBLE_EDGE,
        padding=(0, 1),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "create_progress_bar",
    "StatusItem",
    "render_status_panel",
    "APICandidateItem",
    "render_api_list",
    "StageProgress",
    "render_stage_progress",
    "render_log_panel",
    "render_budget_display",
    "OutputFile",
    "render_output_files",
    "render_command_bar",
]