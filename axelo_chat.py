#!/usr/bin/env python
"""
Axelo Chat CLI - 独立入口点

绕过 platform 模块冲突的独立 CLI
"""
from __future__ import annotations

import asyncio
import sys

# Windows UTF-8 mode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main():
    """主入口"""
    # 直接导入 chat 模块，绕过有问题的 platform 模块
    from axelo.chat.cli import AxeloChatCLI
    
    try:
        asyncio.run(AxeloChatCLI().start())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
