"""
Axelo Logo - Logo 渲染模块
"""

from rich.panel import Panel
from rich.text import Text
from rich.console import Console
from rich.box import Box, DOUBLE, DOUBLE_EDGE

from axelo.ui.theme import ThemeColors


# ═══════════════════════════════════════════════════════════════════════════════
# Logo ASCII 艺术
# ═══════════════════════════════════════════════════════════════════════════════

LOGO_ART = r"""
                    ╭─────────────────────────────────╮
                    │                                 │
                    │      ╭──────────────────╮       │
                    │      │    ████  ████    │       │
                    │      │    ████  ████    │       │
                    │      │    ██ ██ ██ ██   │       │
                    │      │    ██ ██ ██ ██   │       │
                    │      │    ████████████   │       │
                    │      │    ████████████   │       │
                    │      │    ██      ██    │       │
                    │      │    ██      ██    │       │
                    │      ╰──────────────────╯       │
                    │                                 │
                    │      🔷 AXELO                  │
                    │      ──────────                │
                    │      AI-Driven JS Reverse      │
                    │                                 │
                    ╰─────────────────────────────────╯
"""

LOGO_COMPACT = r"""
 ╭─────────────────────────────────╮
 │      ╭──────────────────╮       │
 │      │    ████  ████    │       │
 │      │    ████  ████    │       │
 │      │    ██ ██ ██ ██   │       │
 │      │    ██ ██ ██ ██   │       │
 │      │    ████████████   │       │
 │      │    ████████████   │       │
 │      │    ██      ██    │       │
 │      │    ██      ██    │       │
 │      ╰──────────────────╯       │
 │                                 │
 │      🔷 AXELO                  │
 │      ──────────                │
 │      AI-Driven JS Reverse      │
 ╰─────────────────────────────────╯
"""

LOGO_MINI = r"""
  ╭──────────────────╮
  │    ████  ████    │
  │    ████  ████    │
  │    ██ ██ ██ ██   │
  │    ██ ██ ██ ██   │
  │    ████████████   │
  │    ████████████   │
  │    ██      ██    │
  │    ██      ██    │
  ╰──────────────────╯
       🔷 AXELO
   ───────────────
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Logo 渲染函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_logo(style: str = "full") -> str:
    """获取指定风格的 Logo"""
    styles = {
        "full": LOGO_ART,
        "compact": LOGO_COMPACT,
        "mini": LOGO_MINI,
    }
    return styles.get(style, LOGO_ART)


def render_logo(style: str = "full", color: str = "primary") -> Text:
    """
    渲染 Logo 为 Rich Text
    
    Args:
        style: 样式 (full/compact/mini)
        color: 颜色 (primary/accent/success)
    
    Returns:
        Rich Text 对象
    """
    logo_text = get_logo(style)
    
    # 使用紫色主题
    text = Text(logo_text)
    text.stylize(f"{color}")
    
    return text


def render_logo_panel(title: str = "", subtitle: str = "AI-Driven JS Reverse") -> Panel:
    """
    渲染为 Panel 格式
    
    Args:
        title: 标题
        subtitle: 副标题
    
    Returns:
        Rich Panel 对象
    """
    # Logo 部分 - 使用主色调
    logo = Text(LOGO_COMPACT)
    logo.stylize("primary")
    
    # 标题部分
    if title or subtitle:
        title_text = Text()
        if title:
            title_text.append("      🔷 ", "primary bold")
            title_text.append(title, "primary bold")
            title_text.append("\n      ──────────\n", "text_muted")
        if subtitle:
            title_text.append(f"      {subtitle}", "primary_light")
        
        content = Text("\n") + logo + Text("\n") + title_text
    else:
        content = logo
    
    panel = Panel(
        content,
        box=Box.DOUBLE,
        border_style="primary",
        padding=(0, 1),
        title="",
    )
    
    return panel


def print_logo(console: Console | None = None) -> None:
    """打印 Logo 到控制台"""
    if console is None:
        console = Console()
    
    # 使用 box 样式
    console.print()
    console.print(render_logo("compact", "primary"))
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "get_logo",
    "render_logo",
    "render_logo_panel",
    "print_logo",
    "LOGO_ART",
    "LOGO_COMPACT",
    "LOGO_MINI",
]