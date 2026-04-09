"""
Axelo Animation - 动画效果模块
"""

import asyncio
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


# ═══════════════════════════════════════════════════════════════════════════════
# Spinner 动画
# ═══════════════════════════════════════════════════════════════════════════════

class SpinnerAnimation:
    """旋转动画"""
    
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, message: str = "加载中"):
        self.message = message
        self.frame_index = 0
        self._running = False
    
    @property
    def current_frame(self) -> str:
        return self.FRAMES[self.frame_index % len(self.FRAMES)]
    
    def update(self) -> str:
        """更新动画帧"""
        self.frame_index += 1
        return f"{self.current_frame} {self.message}"
    
    async def run(self, console: Console, duration: float = 5.0):
        """运行动画"""
        self._running = True
        start = asyncio.get_event_loop().time()
        
        with Live(console=console, refresh_per_second=10) as live:
            while self._running:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed > duration:
                    break
                
                live.update(Panel(
                    Text(self.update(), style="primary"),
                    border_style="primary",
                ))
                await asyncio.sleep(0.1)
    
    def stop(self):
        """停止动画"""
        self._running = False


# ═══════════════════════════════════════════════════════════════════════════════
# 脉冲动画
# ═══════════════════════════════════════════════════════════════════════════════

class PulseAnimation:
    """脉冲动画"""
    
    def __init__(self, text: str, color: str = "primary"):
        self.text = text
        self.color = color
        self.frame_index = 0
    
    @property
    def frames(self) -> list[str]:
        return ["●", "○", "◔", "◕", "◉"]
    
    @property
    def current_frame(self) -> str:
        return self.frames[self.frame_index % len(self.frames)]
    
    def update(self) -> str:
        self.frame_index += 1
        return f"[{self.color}]{self.current_frame}[/{self.color}] {self.text}"


# ═══════════════════════════════════════════════════════════════════════════════
# 加载动画
# ═══════════════════════════════════════════════════════════════════════════════

class LoadingAnimation:
    """加载动画 - 带进度条"""
    
    def __init__(self, title: str, total: int = 100):
        self.title = title
        self.total = total
        self.current = 0
        self._running = False
    
    @property
    def percentage(self) -> float:
        return (self.current / self.total) * 100 if self.total > 0 else 0
    
    @property
    def progress_bar(self) -> str:
        bar_width = 30
        filled = int(bar_width * (self.current / self.total)) if self.total > 0 else 0
        return "█" * filled + "░" * (bar_width - filled)
    
    def render(self) -> str:
        return (
            f"{self.title}\n"
            f"[primary]{self.progress_bar}[/primary]  {self.percentage:.0f}%"
        )
    
    async def run(self, console: Console, update_callback=None):
        """运行加载动画"""
        self._running = True
        
        with Live(console=console, refresh_per_second=10) as live:
            while self._running and self.current < self.total:
                live.update(Panel(
                    Text(self.render(), style="primary"),
                    border_style="primary",
                ))
                
                if update_callback:
                    await update_callback()
                else:
                    await asyncio.sleep(0.1)
                
                self.current += 1
        
        # 完成时显示最终状态
        live.update(Panel(
            Text(f"[success]✓ {self.title} 完成[/success]", style="success"),
            border_style="success",
        ))
    
    def stop(self):
        """停止动画"""
        self._running = False
    
    def set_progress(self, current: int, total: int = 100):
        """设置进度"""
        self.current = current
        self.total = total


# ═══════════════════════════════════════════════════════════════════════════════
# 打字机效果
# ═══════════════════════════════════════════════════════════════════════════════

async def type_text(console: Console, text: str, delay: float = 0.03):
    """打字机效果输出"""
    for char in text:
        console.print(char, end="")
        await asyncio.sleep(delay)
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# 闪烁效果
# ═══════════════════════════════════════════════════════════════════════════════

class BlinkAnimation:
    """闪烁动画"""
    
    def __init__(self, text: str, color: str = "primary"):
        self.text = text
        self.color = color
        self.visible = True
    
    @property
    def current(self) -> str:
        if self.visible:
            return f"[{self.color}]{self.text}[/{self.color}]"
        return f"[dim]{' ' * len(self.text)}[/dim]"
    
    def toggle(self):
        """切换可见性"""
        self.visible = not self.visible


# ═══════════════════════════════════════════════════════════════════════════════
# 扫描线动画
# ═══════════════════════════════════════════════════════════════════════════════

class ScanlineAnimation:
    """扫描线动画"""
    
    def __init__(self, width: int = 40):
        self.width = width
        self.position = 0
        self.direction = 1
    
    @property
    def bar(self) -> str:
        # 创建扫描线
        left = "░" * self.position
        right = "░" * (self.width - self.position - 1)
        return f"[{self.width}]({left}▓{right})[/]"
    
    def update(self):
        """更新位置"""
        self.position += self.direction
        
        if self.position >= self.width - 1:
            self.direction = -1
        elif self.position <= 0:
            self.direction = 1


# ═══════════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "SpinnerAnimation",
    "PulseAnimation",
    "LoadingAnimation",
    "type_text",
    "BlinkAnimation",
    "ScanlineAnimation",
]