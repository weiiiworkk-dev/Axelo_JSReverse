"""
Axelo Chat CLI - 主入口

对话式逆向工程 CLI
"""
from __future__ import annotations

import asyncio
import sys
from typing import Optional

# Windows UTF-8 mode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import structlog

from axelo.chat.messages import Message, MessageType
from axelo.chat.router import ConversationRouter
from axelo.chat.ui import SimpleTerminalUI
from axelo.tools.base import get_registry

# Import tools to register them
from axelo.tools import (
    browser_tool,
    fetch_tool,
    static_tool,
    crypto_tool,
    ai_tool,
    codegen_tool,
    verify_tool,
    flow_tool,
    honeypot_tool,
)
# Import web search tool
from axelo.tools import web_search_tool

log = structlog.get_logger()


class AxeloChatCLI:
    """Axelo 对话式 CLI"""
    
    def __init__(self):
        self.ui = SimpleTerminalUI()
        self.router = ConversationRouter()
        self._running = False
        
        # 设置思考回调，显示工具调用过程
        self.router.set_thinking_callback(self._on_thinking)
    
    def _on_thinking(self, thinking: str) -> None:
        """显示思考过程"""
        self.ui.print_thinking(thinking)
    
    async def start(self) -> None:
        """启动 CLI"""
        self._running = True
        
        # AI 驱动的欢迎信息 - 不再硬编码
        welcome = await self.router.process_input("你好")
        self._display_response(welcome)
        
        # 主循环
        while self._running:
            try:
                # 等待用户输入
                user_input = await self._get_input()
                
                if not user_input:
                    self.ui.print_system("请输入内容，或按 Ctrl+C 退出")
                    continue
                
                # 处理输入
                response = await self.router.process_input(user_input)
                
                # 显示响应
                self._display_response(response)
                
            except KeyboardInterrupt:
                self.ui.print_system("正在退出...")
                break
            except EOFError:
                self.ui.print_system("输入结束，正在退出...")
                break
            except Exception as e:
                log.error("cli_error", error=str(e))
                self.ui.print_error(f"发生错误: {str(e)}")
        
        self.ui.print_system("再见！")
    
    async def _run_non_interactive(self, url: str, goal: str) -> None:
        """非交互式运行 - 用于 axelo run 命令"""
        # Set context directly
        self.router.context.url = url
        self.router.context.goal = goal
        
        # Generate and display plan
        plan_message = await self.router._generate_plan()
        self._display_response(plan_message)
        
        # Auto-confirm and execute
        self.ui.print_system("\n[自动确认执行...]")
        result = await self.router.execute_plan()
        
        # Display results
        self.ui.print_system(f"\n执行完成！共执行了 {len(result.get('tools', []))} 个工具")
        
        # Show outputs
        outputs = result.get("outputs", {})
        if "python_code" in outputs:
            code = outputs["python_code"]
            self.ui.print_code(code[:500] + "\n... (truncated)")
        
        self._running = False
    
    async def _get_input(self) -> Optional[str]:
        """获取用户输入"""
        try:
            return input("\n> You: ").strip()
        except EOFError:
            return None
    
    def _display_response(self, response: Message) -> None:
        """显示响应"""
        if response.type == MessageType.AI:
            self.ui.print_ai(response.content)
        elif response.type == MessageType.THINKING:
            self.ui.print_thinking(response.content)
        elif response.type == MessageType.PLAN:
            tools = response.metadata.get("tools", [])
            self.ui.print_plan(response.content, tools)
            self.ui.print_confirm("确认执行? (y/n)")
        elif response.type == MessageType.CONFIRM:
            self.ui.print_confirm(response.content)
        elif response.type == MessageType.SYSTEM:
            self.ui.print_system(response.content)
        elif response.type == MessageType.ERROR:
            self.ui.print_error(response.content)
        else:
            self.ui.print_ai(response.content)


async def main():
    """异步主入口"""
    cli = AxeloChatCLI()
    await cli.start()


def main_sync():
    """同步主入口 - 用于 pyproject.toml 入口点"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
