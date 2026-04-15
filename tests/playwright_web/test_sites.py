"""
Playwright Web 端到端测试 — 8 个电商网站业务完整流程（同步版）。

运行方式:
    # 全部站点（顺序执行）
    pytest tests/playwright_web/ -v --tb=short

    # 指定单个站点
    pytest tests/playwright_web/ -v -k "amazon"

产出物位置:
    workspace/test_runs/{site_name}/{NNNNN}/
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from tests.playwright_web.constants import BASE_URL
from tests.playwright_web.runner import run_site_test
from tests.playwright_web.sites import SITES, SiteConfig


@pytest.mark.parametrize("site", SITES, ids=[s.name for s in SITES])
def test_site_end_to_end(page: Page, site: SiteConfig) -> None:
    """
    对单个网站执行完整的逆向工程任务，验证系统通用能力。

    通过条件:
    - 任务状态为 "completed"（mission_status = completed）
    - 或 trust_score >= 0.5（部分成功，有足够证据）
    """
    report = run_site_test(page, site, BASE_URL)

    # ── 打印报告摘要 ──────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"Site       : {report['site']}")
    print(f"Run        : {report['run_number']:05d}")
    print(f"Status     : {report['status']}")
    print(f"Outcome    : {report['mission_outcome']}")
    print(f"Trust score: {report['trust_score']}")
    print(f"Events     : {report['events_collected']}")
    print(f"Artifacts  : {len(report['engine_artifacts'])} files")
    print(f"Failure    : [{report['failure_category']}] {report['failure_detail']}")
    print(f"Run dir    : {report['run_dir']}")
    print(f"{'='*60}")

    # ── 断言 ─────────────────────────────────────────────────
    assert report["session_id"], (
        f"[{site.name}] 任务未能启动，无 session_id。\n"
        f"失败分类: {report['failure_category']}\n"
        f"详情: {report['failure_detail']}\n"
        f"错误: {report['error_message']}"
    )

    mission_ok = report["status"] == "passed"
    trust_ok = float(report["trust_score"] or 0) >= 0.5

    assert mission_ok or trust_ok, (
        f"[{site.name}] 任务失败且无足够信任分数。\n"
        f"状态: {report['status']}\n"
        f"Trust score: {report['trust_score']} (需要 >= 0.5)\n"
        f"失败分类: {report['failure_category']}\n"
        f"详情: {report['failure_detail']}\n"
        f"产出物目录: {report['run_dir']}"
    )
