"""
Terminal UI 组件

提供 Terminal 对话界面所需的 UI 组件
"""
from __future__ import annotations

import sys
from typing import AsyncGenerator, Callable

# 尝试导入 rich，如果不可用则使用简单版本
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
    from rich.markdown import Markdown
    from rich.syntax import Syntax
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

import structlog

log = structlog.get_logger()


class TerminalUI:
    """Terminal UI 渲染器"""
    
    def __init__(self):
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None
    
    # ============================================================
    # 消息渲染
    # ============================================================
    
    def print_ai(self, content: str, **kwargs) -> None:
        """打印 AI 消息"""
        if RICH_AVAILABLE:
            panel = Panel(
                content,
                title="[bold blue]AI[/bold blue]",
                border_style="blue",
                expand=False,
            )
            self.console.print(panel)
        else:
            print(f"\n🤖 AI: {content}\n")
    
    def print_user(self, content: str) -> None:
        """打印用户消息"""
        if RICH_AVAILABLE:
            self.console.print(f"[bold green]>[/bold green] {content}")
        else:
            print(f"\n👤 用户: {content}\n")
    
    def print_system(self, content: str, **kwargs) -> None:
        """打印系统消息"""
        if RICH_AVAILABLE:
            self.console.print(f"[dim]{content}[/dim]")
        else:
            print(f"\n📢 系统: {content}\n")
    
    def print_error(self, content: str) -> None:
        """打印错误消息"""
        if RICH_AVAILABLE:
            self.console.print(f"[bold red]错误:[/bold red] {content}")
        else:
            print(f"\n❌ 错误: {content}\n")
    
    def print_thinking(self, content: str) -> None:
        """打印思考过程"""
        if RICH_AVAILABLE:
            self.console.print(f"[dim blue]💭 {content}[/dim blue]")
        else:
            print(f"💭 {content}")
    
    # ============================================================
    # 计划渲染
    # ============================================================
    
    def print_plan(self, plan_text: str, tools: list[str]) -> None:
        """打印执行计划"""
        if RICH_AVAILABLE:
            table = Table(title="📋 执行计划", show_header=True)
            table.add_column("序号", style="cyan", justify="right")
            table.add_column("Tool", style="magenta")
            
            for i, tool in enumerate(tools, 1):
                table.add_row(str(i), tool)
            
            self.console.print(table)
            if plan_text:
                self.console.print(f"\n[dim]{plan_text}[/dim]")
        else:
            print("\n📋 执行计划:")
            for i, tool in enumerate(tools, 1):
                print(f"  {i}. {tool}")
    
    def print_confirm(self, message: str = "确认执行? (y/n)") -> None:
        """打印确认请求"""
        if RICH_AVAILABLE:
            self.console.print(f"[bold yellow]❓ {message}[/bold yellow]")
        else:
            print(f"\n❓ {message}")
    
    # ============================================================
    # 进度条
    # ============================================================
    
    def create_progress(self) -> "Progress | None":
        """创建进度条"""
        if RICH_AVAILABLE:
            return Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=self.console,
            )
        return None
    
    # ============================================================
    # Markdown 渲染
    # ============================================================
    
    def print_markdown(self, content: str) -> None:
        """渲染 Markdown"""
        if RICH_AVAILABLE:
            md = Markdown(content)
            self.console.print(md)
        else:
            print(content)
    
    # ============================================================
    # 代码渲染
    # ============================================================
    
    def print_code(self, code: str, language: str = "python") -> None:
        """渲染代码"""
        if RICH_AVAILABLE:
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            self.console.print(syntax)
        else:
            print(f"\n```{language}\n{code}\n```\n")
    
    # ============================================================
    # 表格渲染
    # ============================================================
    
    def print_table(self, data: list[dict], title: str = "") -> None:
        """渲染表格"""
        if not data:
            return
            
        if RICH_AVAILABLE:
            table = Table(title=title, show_header=True)
            for key in data[0].keys():
                table.add_column(key, style="cyan")
            
            for row in data:
                table.add_row(*[str(v) for v in row.values()])
            
            self.console.print(table)
        else:
            print(f"\n{title}")
            for row in data:
                print(row)
    
    # ============================================================
    # 工具执行状态
    # ============================================================
    
    def print_tool_start(self, tool_name: str) -> None:
        """打印工具开始执行"""
        if RICH_AVAILABLE:
            self.console.print(f"[cyan]⚡ 执行工具:[/cyan] {tool_name}")
        else:
            print(f"\n⚡ 执行工具: {tool_name}")
    
    def print_tool_result(self, tool_name: str, success: bool, duration: float) -> None:
        """打印工具执行结果"""
        if RICH_AVAILABLE:
            status = "[green]✓ 成功[/green]" if success else "[red]✗ 失败[/red]"
            self.console.print(f"  {status} ({duration:.1f}s)")
        else:
            status = "✓ 成功" if success else "✗ 失败"
            print(f"  {status} ({duration:.1f}s)")


# 全局 UI 实例
_ui: TerminalUI | None = None


def get_ui() -> TerminalUI:
    """获取全局 UI 实例"""
    global _ui
    if _ui is None:
        _ui = TerminalUI()
    return _ui


# ============================================================
# 简化的非 Rich 版本 (ASCII only for Windows compatibility)
# ============================================================

class SimpleTerminalUI:
    """不使用 Rich 库的简化版本"""
    
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    DIM = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    # 分隔线样式
    DIVIDER = "─"
    DIVIDER_THIN = "─"
    DIVIDER_MD = "─"
    DIVIDER_THICK = "━"
    DECOR_LEFT = "◈"
    DECOR_RIGHT = "◈"
    
    @classmethod
    def _divider(cls, style: str = "thin") -> str:
        """生成分隔线"""
        width = 60
        if style == "thick":
            return f"{cls.DIM}{cls.DIVIDER_THICK * width}{cls.RESET}"
        elif style == "decor":
            return f"{cls.DIM}{cls.DECOR_LEFT}{cls.DIVIDER_THICK * (width-2)}{cls.DECOR_RIGHT}{cls.RESET}"
        else:
            return f"{cls.DIM}{cls.DIVIDER_THIN * width}{cls.RESET}"
    
    @classmethod
    def _separator(cls) -> str:
        """输出后的小分隔线"""
        return f"{cls.DIM}· · · · · · · · · · · · · · · · · · · · · · · · ·{cls.RESET}"
    
    def print_ai(self, content: str) -> None:
        print(f"\n{self.BLUE}{self.BOLD}[ AI ]{self.RESET} {content}")
        print(self._separator())
    
    def print_user(self, content: str) -> None:
        print(f"\n{self.GREEN}{self.BOLD}[ You ]{self.RESET} {content}")
        print(self._separator())
    
    def print_system(self, content: str) -> None:
        print(f"\n{self.DIM}▸ {content}{self.RESET}")
        print(self._separator())
    
    def print_error(self, content: str) -> None:
        print(f"\n{self.RED}{self.BOLD}✕ Error{self.RESET} {content}")
        print(self._separator())
    
    def print_thinking(self, content: str) -> None:
        print(f"{self.CYAN}💭 {content}{self.RESET}")
    
    def print_plan(self, plan_text: str, tools: list[str]) -> None:
        print(f"\n{self.MAGENTA}{self.BOLD}⟡ Execution Plan{self.RESET}")
        print(self._divider("thin"))
        for i, tool in enumerate(tools, 1):
            print(f"  {self.CYAN}{i}.{self.RESET} {tool}")
        print(self._divider("thin"))
    
    def print_confirm(self, message: str = "Confirm? (y/n)") -> None:
        print(f"\n{self.YELLOW}{self.BOLD}? {message}{self.RESET}")
    
    def print_tool_start(self, tool_name: str) -> None:
        print(f"\n{self.CYAN}⚡ {tool_name}{self.RESET}")
        print(self._divider("thin"))
    
    def print_tool_result(self, tool_name: str, success: bool, duration: float) -> None:
        status = f"{self.GREEN}✓ Success{self.RESET}" if success else f"{self.RED}✕ Failed{self.RESET}"
        print(f"  {status} ({duration:.1f}s)")
        print(self._separator())
    
    def print_code(self, code: str, language: str = "python") -> None:
        print(f"\n{self.MAGENTA}┌─ Code Output ({language}){self.RESET}")
        print(self._divider("thin"))
        print(code)
        print(self._divider("thin"))
