"""
Axelo Discovery Screen - API 发现页
"""

from dataclasses import dataclass, field
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text

from axelo.ui.logo import LOGO_MINI
from axelo.ui.components import (
    StatusItem,
    render_status_panel,
    APICandidateItem,
    render_api_list,
    render_command_bar,
)


@dataclass
class DiscoveryState:
    """发现过程状态"""
    site: str = ""
    status_items: List[StatusItem] = field(default_factory=list)
    api_candidates: List[APICandidateItem] = field(default_factory=list)
    progress: float = 0.0  # 0.0 - 1.0
    is_complete: bool = False


def show_site_recognition(console: Console, site: str) -> None:
    """显示站点识别过程"""
    
    console.print()
    console.print(f"🔍 正在识别: [primary]{site}[/]")
    console.print("─" * 60)
    
    # 站点识别状态
    status = [
        StatusItem("域名解析", "success", site),
        StatusItem("站点画像", "success", "e-commerce-cn"),
        StatusItem("反爬检测", "info", "自定义签名"),
        StatusItem("登录检测", "pending", "需要Cookie"),
    ]
    
    console.print(render_status_panel("站点识别", status))


def show_discovery_progress(console: Console, progress: float, found_count: int = 0) -> None:
    """显示发现进度"""
    
    bar_width = 30
    filled = int(bar_width * progress)
    bar = "█" * filled + "░" * (bar_width - filled)
    
    console.print()
    console.print(f"🚀 正在发现 API...  [primary]{bar}[/]  {progress * 100:.0f}%")
    if found_count > 0:
        console.print(f"   发现 [primary]{found_count}[/] 个端点")


def show_api_candidates(console: Console, candidates: List[APICandidateItem], 
                         show_all: bool = False) -> None:
    """显示 API 候选列表"""
    
    if not candidates:
        return
    
    # 只显示前5个或全部
    display_candidates = candidates[:5] if not show_all else candidates
    
    console.print()
    console.print(render_api_list(display_candidates))
    
    if len(candidates) > 5 and not show_all:
        console.print(f"   [dim]还有 {len(candidates) - 5} 个 API...[/dim]")


def show_discovery_result(console: Console, site: str, candidates: List[APICandidateItem],
                          total_requests: int, success_requests: int,
                          protected_apis: int, duration: float) -> None:
    """显示发现结果"""
    
    console.print()
    console.print(f"✅ 发现完成 - [bold #9333EA]{site}[/]")
    console.print("─" * 60)
    
    # 统计信息
    stats_table = Text()
    stats_table.append("📊 发现统计\n", style="bold #9333EA")
    stats_table.append("─" * 40 + "\n", style="#7C3AED")
    stats_table.append(f"  总请求数:    {total_requests}\n", style="#E9D5FF")
    stats_table.append(f"  成功:        {success_requests}\n", style="#E9D5FF")
    stats_table.append(f"  保护API:     {protected_apis}\n", style="#E9D5FF")
    stats_table.append(f"  目标API:     {len(candidates)}\n", style="#E9D5FF")
    stats_table.append(f"  时长:        {duration:.1f}s\n", style="#E9D5FF")
    
    console.print(Panel(stats_table, border_style="#22C55E", padding=(1, 2)))
    
    # 显示目标 API
    if candidates:
        console.print()
        console.print("🎯 目标 API (已推荐)", style="bold #9333EA")
        console.print("─" * 40)
        
        # 标记推荐项
        for i, candidate in enumerate(candidates[:3], 1):
            recommended = "⭐ " if i <= 2 else "   "
            method_color = "#22C55E" if candidate.method == "GET" else "#FBBF24"
            
            console.print()
            console.print(f"{recommended}#[{i}] ", style="#9333EA", end="")
            console.print(f"URL:   ", style="#7C3AED", end="")
            console.print(f"[{method_color}]{candidate.method}[/] ", end="")
            console.print(candidate.url)
            
            console.print(f"       保护:  ", style="#7C3AED", end="")
            console.print(candidate.protection if candidate.protection else "无")
            
            console.print(f"       置信度: ", style="#7C3AED", end="")
            if candidate.confidence >= 0.9:
                console.print(f"[#22C55E]{candidate.confidence * 100:.0f}%[/]")
            elif candidate.confidence >= 0.7:
                console.print(f"[#9333EA]{candidate.confidence * 100:.0f}%[/]")
            else:
                console.print(f"[#FBBF24]{candidate.confidence * 100:.0f}%[/]")
    
    # 命令提示
    console.print()
    console.print(render_command_bar([
        "[1-3] 选择API",
        "[A] 全部逆向",
        "[S] 保存结果",
        "[Q] 退出"
    ]))


def show_discovery_header(console: Console, site: str, subtitle: str = "逆向 & 爬虫") -> None:
    """显示发现页面头部 - 带 Logo"""
    
    # Logo
    logo_text = Text(LOGO_MINI)
    logo_text.stylize("primary")
    
    # 标题
    header = Text()
    header.append(logo_text)
    header.append("\n")
    header.append(f"      🔷 AXELO  -  {subtitle}\n", style="primary bold")
    header.append(f"      {site}", style="primary_light")
    
    console.print(header)


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "DiscoveryState",
    "show_site_recognition",
    "show_discovery_progress",
    "show_api_candidates",
    "show_discovery_result",
    "show_discovery_header",
]