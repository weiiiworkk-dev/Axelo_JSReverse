"""
Axelo Result Screen - 结果展示页
"""

from dataclasses import dataclass, field
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from axelo.ui.logo import LOGO_MINI
from axelo.ui.components import (
    OutputFile,
    render_output_files,
    render_command_bar,
)


@dataclass
class ResultState:
    """结果状态"""
    site: str = ""
    api_path: str = ""
    output_files: List[OutputFile] = field(default_factory=list)
    signature_algorithm: str = ""
    signature_params: str = ""
    signature_example: str = ""
    total_cost: float = 0.0
    session_id: str = ""
    duration: float = 0.0


def show_result_header(console: Console, site: str, api_path: str) -> None:
    """显示结果页面头部"""
    
    # Logo
    logo_text = Text(LOGO_MINI)
    logo_text.stylize("primary")
    
    # 标题
    header = Text()
    header.append("\n")
    header.append(logo_text)
    header.append("\n\n")
    header.append("✅ 逆向完成\n", style="success bold")
    header.append("─" * 40 + "\n", style="text_muted")
    header.append(f"  {site} ", style="primary")
    header.append(f"{api_path}", style="primary_light")
    
    console.print(header)


def show_output_files(console: Console, files: List[OutputFile]) -> None:
    """显示输出文件列表"""
    
    if not files:
        return
    
    console.print(render_output_files(files))


def show_signature_analysis(console: Console, algorithm: str, params: str, 
                             example: str) -> None:
    """显示签名分析结果"""
    
    content = Text()
    content.append("🔍 签名分析\n", style="primary bold")
    content.append("─" * 40 + "\n", style="text_muted")
    content.append(f"\n", style="text_primary")
    content.append(f"  算法:  ", style="text_muted")
    content.append(f"{algorithm}\n", style="success")
    content.append(f"\n", style="text_primary")
    content.append(f"  参数:  ", style="text_muted")
    content.append(f"{params}\n", style="text_primary")
    content.append(f"\n", style="text_primary")
    content.append(f"  密钥:  ", style="text_muted")
    content.append(f"从 JS 中提取 (硬编码)\n", style="text_primary")
    content.append(f"\n", style="text_primary")
    content.append(f"  示例:  ", style="text_muted")
    content.append(f"\n", style="text_primary")
    content.append(f"    {example}\n", style="primary_light")
    
    console.print(Panel(
        content,
        title=" 签名分析 ",
        border_style="primary",
        padding=(1, 2),
    ))


def show_result_stats(console: Console, cost: float, session_id: str, duration: float) -> None:
    """显示结果统计"""
    
    stats = Text()
    stats.append(f"💰 总消耗: ", style="text_muted")
    stats.append(f"${cost:.2f}", style="primary bold")
    stats.append(f"  |  ", style="text_muted")
    stats.append(f"⏱️  时长: ", style="text_muted")
    stats.append(f"{duration:.1f}s", style="text_primary")
    stats.append(f"  |  ", style="text_muted")
    stats.append(f"📋 Session: ", style="text_muted")
    stats.append(f"{session_id}", style="primary_light")
    
    console.print()
    console.print(Panel(
        stats,
        border_style="primary",
        padding=(0, 2),
    ))


def show_result_command_bar(console: Console) -> None:
    """显示结果页面命令栏"""
    
    console.print()
    console.print(render_command_bar([
        "[R] 运行爬虫",
        "[E] 编辑代码",
        "[S] 保存到文件",
        "[Q] 退出"
    ]))


# ═══════════════════════════════════════════════════════════════════════════════
# 模拟数据 - 用于演示
# ═══════════════════════════════════════════════════════════════════════════════

DEMO_OUTPUT_FILES = [
    OutputFile("crawler.py", "2.3KB", "success"),
    OutputFile("bridge_server.js", "4.1KB", "success"),
    OutputFile("requirements.txt", "156B", "success"),
    OutputFile("manifest.json", "1.2KB", "success"),
    OutputFile("verify_report.json", "2.8KB", "success"),
]

DEMO_SIGNATURE = {
    "algorithm": "HMAC-SHA256",
    "params": "app_id + timestamp + nonce",
    "example": "sign = HMAC(\"key\", app_id + timestamp + nonce)",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "ResultState",
    "show_result_header",
    "show_output_files",
    "show_signature_analysis",
    "show_result_stats",
    "show_result_command_bar",
    "DEMO_OUTPUT_FILES",
    "DEMO_SIGNATURE",
]