"""
共享测试常量 — 从 tests/shared_port.py 统一导入端口配置。

历史问题：本文件曾自己调用 _find_free_port()，导致与 tests/conftest.py
中的端口不同，runner.py 在测试时连接到错误的服务地址。

现在统一从 shared_port 导入，保证整个 pytest 会话只有一个端口。
"""
from __future__ import annotations

from tests.shared_port import TEST_PORT, BASE_URL  # noqa: F401
