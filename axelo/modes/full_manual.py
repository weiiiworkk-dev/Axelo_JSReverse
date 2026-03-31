from __future__ import annotations
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from axelo.models.pipeline import Decision, PipelineState
from axelo.modes.base import ModeController

console = Console()


class ManualMode(ModeController):
    """
    全手动模式：AI 仅提供建议，人工明确执行每一步。
    每个决策展示 AI 建议但不预设默认值。
    """
    name = "manual"

    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        return False

    async def gate(self, decision: Decision, state: PipelineState) -> str:
        await asyncio.get_event_loop().run_in_executor(None, self._render, decision)
        return await asyncio.get_event_loop().run_in_executor(None, self._prompt, decision)

    def _render(self, decision: Decision) -> None:
        console.print()
        suggestion = f"\n[dim]AI 建议: {decision.default}[/dim]" if decision.default else ""
        body = f"[white]{decision.prompt}[/white]{suggestion}"
        if decision.options:
            opts = "\n".join(f"  ({i}) {o}" for i, o in enumerate(decision.options, 1))
            body += f"\n\n{opts}"
        console.print(Panel(body, title=f"[bold magenta]手动模式 — {decision.stage}[/bold magenta]", border_style="magenta"))
        console.print("[dim]输入选项编号，或 'skip' 跳过，'quit' 退出[/dim]")

    def _prompt(self, decision: Decision) -> str:
        if decision.options:
            choices = [str(i) for i in range(1, len(decision.options) + 1)] + ["skip", "quit"]
            raw = Prompt.ask("[bold]你的选择[/bold]", choices=choices)
        else:
            raw = Prompt.ask("[bold]确认执行（run/skip/quit）[/bold]", choices=["run", "skip", "quit"])

        if raw == "quit":
            raise KeyboardInterrupt
        if raw in ("skip",):
            return "skip"
        if raw == "run":
            return "y"
        if decision.options and raw.isdigit():
            return decision.options[int(raw) - 1]
        return raw
