"""共享测试常量 — 模块级，只计算一次。

通过此文件统一导出 TEST_PORT 和 BASE_URL，
避免 conftest.py 被 pytest 自动加载与 import 语句两次实例化导致端口不一致。
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
