"""
共享端口配置 — 所有测试模块的单一端口来源。

解决问题：tests/conftest.py 与 tests/playwright_web/conftest.py 曾各自调用
_find_free_port()，每次都随机分配不同端口，导致：
  1. 两个子进程分别启动了两份 axelo web server
  2. playwright_web/constants.py 中的 BASE_URL 与顶层 conftest.py 中的
     BASE_URL 不同，runner.py 连接错误的服务端口

解决方式：全部测试模块统一从本文件 import TEST_PORT / BASE_URL，
保证整个 pytest 会话只有一个端口、一个服务进程。
"""
from __future__ import annotations

import socket


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


TEST_PORT: int = _find_free_port()
BASE_URL: str = f"http://localhost:{TEST_PORT}"
