from __future__ import annotations
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich import box

from axelo.models.pipeline import Decision, DecisionType, PipelineState
from axelo.modes.base import ModeController

console = Console()

# 高置信度自动跳过阈值
AUTO_PROCEED_THRESHOLD = 0.95


class InteractiveMode(ModeController):
    """
    默认模式：展示 Rich UI，人工授权每个决策点。
    当 AI 置信度超过阈值时可自动跳过低风险决策。
    """
    name = "interactive"

    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        return confidence >= AUTO_PROCEED_THRESHOLD

    async def gate(self, decision: Decision, state: PipelineState) -> str:
        await asyncio.get_event_loop().run_in_executor(None, self._render, decision, state)
        return await asyncio.get_event_loop().run_in_executor(None, self._prompt, decision)

    def _render(self, decision: Decision, state: PipelineState) -> None:
        console.print()
        title = f"[bold cyan]阶段 {decision.stage}[/bold cyan] — [yellow]{decision.decision_type.value}[/yellow]"

        content_lines = [f"[white]{decision.prompt}[/white]"]

        if decision.context_summary:
            content_lines.append(f"\n[dim]{decision.context_summary}[/dim]")

        if decision.options:
            content_lines.append("")
            for i, opt in enumerate(decision.options, 1):
                content_lines.append(f"  [bold green]({i})[/bold green] {opt}")

        if decision.artifact_path and decision.artifact_path.exists():
            content_lines.append(f"\n[dim]文件: {decision.artifact_path}[/dim]")
            try:
                code = decision.artifact_path.read_text(encoding="utf-8")[:3000]
                suffix = decision.artifact_path.suffix.lstrip(".") or "text"
                console.print(Panel("\n".join(content_lines), title=title, border_style="cyan"))
                console.print(Syntax(code, suffix, theme="monokai", line_numbers=True))
                return
            except Exception:
                pass

        console.print(Panel("\n".join(content_lines), title=title, border_style="cyan"))

        # 操作提示
        hints = Table.grid(padding=(0, 2))
        hints.add_row(
            "[dim]Enter/y[/dim] 确认",
            "[dim]n[/dim] 拒绝/重选",
            "[dim]s[/dim] 跳过此阶段",
            "[dim]v[/dim] 查看文件",
            "[dim]q[/dim] 退出并保存",
        )
        console.print(hints)

    def _prompt(self, decision: Decision) -> str:
        if decision.options:
            choices = [str(i) for i in range(1, len(decision.options) + 1)]
            choices += ["s", "q"]
            raw = Prompt.ask(
                "[bold]选择[/bold]",
                choices=choices,
                default=decision.default or choices[0],
            )
            if raw == "s":
                return "skip"
            if raw == "q":
                raise KeyboardInterrupt
            return decision.options[int(raw) - 1]
        else:
            raw = Prompt.ask(
                "[bold]确认继续？[/bold]",
                choices=["y", "n", "s", "q"],
                default=decision.default or "y",
            )
            if raw == "q":
                raise KeyboardInterrupt
            if raw == "s":
                return "skip"
            return raw
