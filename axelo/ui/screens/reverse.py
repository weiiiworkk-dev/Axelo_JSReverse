"""
Axelo Reverse Screen - 逆向执行页
"""

from dataclasses import dataclass, field
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from axelo.ui.logo import LOGO_MINI
from axelo.ui.components import (
    StageProgress,
    render_stage_progress,
    render_log_panel,
    render_budget_display,
    render_command_bar,
)


@dataclass
class ReverseState:
    """逆向过程状态"""
    target_url: str = ""
    method: str = "GET"
    stages: List[StageProgress] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    budget_used: float = 0.0
    budget_total: float = 2.0
    is_complete: bool = False


def show_reverse_header(console: Console, method: str, url: str) -> None:
    """显示逆向页面头部"""
    
    # Logo
    logo_text = Text(LOGO_MINI)
    logo_text.stylize("primary")
    
    # 标题
    header = Text()
    header.append(logo_text)
    header.append("\n")
    header.append("      🔷 AXELO  -  逆向 & 爬虫\n", style="primary bold")
    header.append("      ────────────────────\n", style="text_muted")
    header.append(f"      {method} ", style="success" if method == "GET" else "warning")
    header.append(url[:50] + "..." if len(url) > 50 else url, style="primary_light")
    
    console.print(header)


def show_stage_progress(console: Console, stages: List[StageProgress]) -> None:
    """显示阶段进度"""
    
    console.print(render_stage_progress(stages))


def show_reverse_logs(console: Console, logs: List[str], max_lines: int = 8) -> None:
    """显示执行日志"""
    
    if not logs:
        return
    
    # 只显示最近的日志
    display_logs = logs[-max_lines:] if len(logs) > max_lines else logs
    
    content = Text()
    for log in display_logs:
        # 解析日志
        if "]" in log:
            parts = log.split("]", 1)
            timestamp = parts[0] + "]"
            content.append(f"[text_muted]{timestamp}[/] ", style="dim")
            
            # 检查日志内容类型
            content_str = parts[1] if len(parts) > 1 else ""
            
            # 根据关键词着色
            if "🔍" in content_str or "分析" in content_str:
                content.append(content_str + "\n", style="primary")
            elif "📦" in content_str or "下载" in content_str:
                content.append(content_str + "\n", style="primary_light")
            elif "🔬" in content_str or "静态" in content_str:
                content.append(content_str + "\n", style="info")
            elif "🎣" in content_str or "Hook" in content_str:
                content.append(content_str + "\n", style="warning")
            elif "✅" in content_str or "成功" in content_str:
                content.append(content_str + "\n", style="success")
            elif "❌" in content_str or "失败" in content_str:
                content.append(content_str + "\n", style="error")
            else:
                content.append(content_str + "\n", style="text_primary")
        else:
            content.append(log + "\n", style="text_primary")
    
    console.print(Panel(
        content,
        title=" 执行日志 ",
        border_style="primary",
        padding=(1, 2),
    ))


def show_budget(console: Console, used: float, total: float) -> None:
    """显示预算消耗"""
    
    console.print(render_budget_display(used, total))


def show_reverse_complete(console: Console, url: str, session_id: str,
                          total_cost: float, duration: float) -> None:
    """显示逆向完成"""
    
    # Logo + 完成信息
    logo_text = Text(LOGO_MINI)
    logo_text.stylize("primary")
    
    result = Text()
    result.append("\n")
    result.append(logo_text)
    result.append("\n\n")
    result.append("✅ 逆向完成\n", style="success bold")
    result.append("─" * 40 + "\n", style="text_muted")
    result.append(f"  目标: {url}\n", style="text_primary")
    result.append(f"  Session: {session_id}\n", style="text_primary")
    result.append(f"\n", style="text_primary")
    result.append(f"  💰 总消耗: [primary]${total_cost:.2f}[/]\n", style="primary")
    result.append(f"  ⏱️  时长: {duration:.1f}s\n", style="text_primary")
    
    console.print(Panel(
        result,
        border_style="success",
        padding=(2, 4),
    ))


def show_reverse_command_bar(console: Console) -> None:
    """显示逆向页面命令栏"""
    
    console.print(render_command_bar([
        "[Ctrl+C] 暂停",
        "[S] 保存进度",
        "[V] 查看代码",
        "[Q] 放弃"
    ]))


# ═══════════════════════════════════════════════════════════════════════════════
# 模拟数据 - 用于演示
# ═══════════════════════════════════════════════════════════════════════════════

DEMO_STAGES = [
    StageProgress("抓取Bundle", 1.0, "completed"),
    StageProgress("静态分析", 0.7, "running"),
    StageProgress("动态验证", 0.0, "pending"),
    StageProgress("代码生成", 0.0, "pending"),
    StageProgress("验证重放", 0.0, "pending"),
]

DEMO_LOGS = [
    "[14:23:15] 🔍 分析请求参数: sign, timestamp, app_id",
    "[14:23:18] 📦 下载 JS Bundle: main.8a2f.js (245KB)",
    "[14:23:22] 🔬 静态分析: 发现 3 个加密函数 (HMAC-SHA256)",
    "[14:23:25] 🎣 Hook 注入成功: window.signature",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ReverseState",
    "show_reverse_header",
    "show_stage_progress",
    "show_reverse_logs",
    "show_budget",
    "show_reverse_complete",
    "show_reverse_command_bar",
    "DEMO_STAGES",
    "DEMO_LOGS",
]