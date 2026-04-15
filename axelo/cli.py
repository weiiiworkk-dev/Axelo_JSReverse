from __future__ import annotations

import asyncio
import sys

import structlog
import typer
from rich.console import Console
from rich.panel import Panel

# Windows UTF-8 support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="axelo",
    help="AI 驱动的网页 JS 逆向系统",
    no_args_is_help=False,
)
console = Console()


def _setup_logging(log_level: str = "info") -> None:
    import logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
    )


@app.callback(invoke_without_command=True)
def default_command(
    ctx: typer.Context,
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动 AI 驱动的逆向向导界面。"""
    if ctx.invoked_subcommand is None:
        _setup_logging(log_level)
        from axelo.chat.cli import AxeloChatCLI
        asyncio.run(AxeloChatCLI().start())


@app.command()
def web(
    port: int = typer.Option(7788, "--port", "-p", help="监听端口"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="启动后自动在浏览器打开（默认开启）"),
    log_level: str = typer.Option("info", "--log-level", "-l", help="日志级别"),
) -> None:
    """启动 AI 逆向向导 Web 服务。"""
    _setup_logging(log_level)
    console.print(
        Panel(
            f"[white]Web 服务端口:[/white] [cyan]{port}[/cyan]\n"
            f"[white]前端地址:[/white] [green]http://localhost:{port}[/green]\n"
            f"[white]API 文档:[/white] [dim]http://localhost:{port}/docs[/dim]",
            title="[bold cyan]Axelo Web — AI 逆向向导[/bold cyan]",
            border_style="cyan",
        )
    )
    from axelo.web.server import run_server
    run_server(port=port, open_browser=open_browser)


if __name__ == "__main__":
    app()
