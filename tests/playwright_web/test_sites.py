"""
[已整合] 本文件的测试已全部合并至 tests/test_suite.py（Part 4b）。

运行方式（统一入口）:
    # 完整测试套件（含所有 10 个硬目标站点）
    pytest tests/test_suite.py -v

    # 仅运行 10 个硬目标 E2E 测试
    pytest tests/test_suite.py -v -k "hard_target"

    # 指定单个站点
    pytest tests/test_suite.py -v -k "google_search"

本文件保留以避免 CI 报告中断，但不包含任何测试函数。
"""
