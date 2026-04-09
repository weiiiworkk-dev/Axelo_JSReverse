"""
Axelo Purple Theme - 紫色主题配置
"""

from rich.console import Console


# ═══════════════════════════════════════════════════════════════════════════════
# 紫色主题配色方案
# ═══════════════════════════════════════════════════════════════════════════════

class ThemeColors:
    """主题颜色类"""
    
    # 主色调
    PRIMARY = "#9333EA"          # 主紫色
    PRIMARY_DARK = "#7E22CE"    # 深紫色
    PRIMARY_LIGHT = "#A855F7"   # 浅紫色
    
    # 背景色
    BACKGROUND = "#0F0A1A"      # 深黑紫背景
    SURFACE = "#1A1225"         # 卡片背景
    SURFACE_ELEVATED = "#241830" # 悬浮背景
    
    # 文字色
    TEXT_PRIMARY = "#E9D5FF"    # 主文字 (淡紫白)
    TEXT_SECONDARY = "#A78BFA"  # 次要文字
    TEXT_MUTED = "#7C3AED"      # 弱化文字
    
    # 强调色
    ACCENT = "#C084FC"          # 强调紫
    SUCCESS = "#22C55E"         # 成功绿
    WARNING = "#FBBF24"        # 警告黄
    ERROR = "#EF4444"           # 错误红
    INFO = "#3B82F6"            # 信息蓝
    
    # 边框/装饰
    BORDER = "#4C1D95"          # 边框紫
    GLOW = "#A855F7"            # 发光效果
    
    # 渐变
    GRADIENT_START = "#9333EA"
    GRADIENT_END = "#C084FC"


# ═══════════════════════════════════════════════════════════════════════════════
# 样式常量 (用于 Rich 标记)
# ═══════════════════════════════════════════════════════════════════════════════

# 使用 Rich 标准颜色 + 自定义十六进制颜色
STYLES = {
    # 主色调
    "primary": ThemeColors.PRIMARY,
    "primary_dark": ThemeColors.PRIMARY_DARK,
    "primary_light": ThemeColors.PRIMARY_LIGHT,
    
    # 文字
    "text_primary": ThemeColors.TEXT_PRIMARY,
    "text_secondary": ThemeColors.TEXT_SECONDARY,
    "text_muted": ThemeColors.TEXT_MUTED,
    
    # 状态
    "accent": ThemeColors.ACCENT,
    "success": ThemeColors.SUCCESS,
    "warning": ThemeColors.WARNING,
    "error": ThemeColors.ERROR,
    "info": ThemeColors.INFO,
    
    # 边框
    "border": ThemeColors.BORDER,
    "glow": ThemeColors.GLOW,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Console 实例
# ═══════════════════════════════════════════════════════════════════════════════

def create_console() -> Console:
    """创建配置好的 Console 实例"""
    return Console(
        color_system="256",
        force_terminal=True,
        width=100,
        height=35,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 样式生成器
# ═══════════════════════════════════════════════════════════════════════════════

def primary(text: str) -> str:
    """主色调文字"""
    return f"[{ThemeColors.PRIMARY}]{text}[/{ThemeColors.PRIMARY}]"


def primary_light(text: str) -> str:
    """浅紫色文字"""
    return f"[{ThemeColors.PRIMARY_LIGHT}]{text}[/{ThemeColors.PRIMARY_LIGHT}]"


def success(text: str) -> str:
    """成功绿色文字"""
    return f"[{ThemeColors.SUCCESS}]{text}[/{ThemeColors.SUCCESS}]"


def warning(text: str) -> str:
    """警告黄色文字"""
    return f"[{ThemeColors.WARNING}]{text}[/{ThemeColors.WARNING}]"


def error(text: str) -> str:
    """错误红色文字"""
    return f"[{ThemeColors.ERROR}]{text}[/{ThemeColors.ERROR}]"


def gradient_text(text: str) -> str:
    """渐变效果文字 (简化为紫色)"""
    return f"[{ThemeColors.PRIMARY_LIGHT}]{text}[/{ThemeColors.PRIMARY_LIGHT}]"


def glow_text(text: str) -> str:
    """发光效果文字"""
    return f"[{ThemeColors.PRIMARY} bold]{text}[/{ThemeColors.PRIMARY}]"


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

theme = ThemeColors()

__all__ = [
    "ThemeColors",
    "STYLES",
    "create_console",
    "primary",
    "primary_light",
    "success",
    "warning",
    "error",
    "gradient_text",
    "glow_text",
    "theme",
]