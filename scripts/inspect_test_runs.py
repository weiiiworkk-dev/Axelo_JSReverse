#!/usr/bin/env python3
"""查看测试运行产出物的汇总信息。

用法:
    python scripts/inspect_test_runs.py              # 汇总所有站点
    python scripts/inspect_test_runs.py amazon       # 只看 amazon
    python scripts/inspect_test_runs.py amazon 3     # 看 amazon 第 3 次运行详情
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from axelo.testing.test_artifact_manager import list_test_runs, summarize_all_runs


def _color(text: str, code: int) -> str:
    return f"\033[{code}m{text}\033[0m"


def _status_color(status: str) -> str:
    colors = {"passed": 32, "failed": 31, "error": 33, "running": 36}
    return _color(status, colors.get(status, 37))


def show_summary() -> None:
    summary = summarize_all_runs()
    if not summary:
        print("暂无测试运行记录。请先执行: pytest tests/playwright_web/")
        return
    print(f"\n{'─'*70}")
    print(f"{'站点':<15} {'总轮次':<8} {'最新状态':<10} {'编号':<8} {'Trust':<8} {'结果'}")
    print(f"{'─'*70}")
    for site, info in sorted(summary.items()):
        status = info["latest_status"] or "unknown"
        print(
            f"{site:<15} {info['total_runs']:<8} {_status_color(status):<10} "
            f"{'#'+str(info['latest_run']):<8} {float(info['latest_trust'] or 0):<8.2f} "
            f"{info['latest_outcome'] or ''}"
        )
    print(f"{'─'*70}\n")


def show_site(site_name: str, run_number: int | None = None) -> None:
    runs = list_test_runs(site_name)
    if not runs:
        print(f"站点 '{site_name}' 暂无测试记录。")
        return

    if run_number is not None:
        target = next((r for r in runs if r.get("run_number") == run_number), None)
        if target is None:
            print(f"未找到 {site_name} 第 {run_number} 次运行记录。")
            return
        _print_run_detail(target)
        return

    print(f"\n站点: {site_name} — 共 {len(runs)} 次运行\n")
    for run in runs:
        status = run.get("status", "?")
        print(
            f"  #{run.get('run_number'):05d} | {_status_color(status):<6} | "
            f"trust={float(run.get('trust_score') or 0):.2f} | "
            f"events={run.get('events_collected', 0)} | "
            f"artifacts={len(run.get('engine_artifacts', []))} | "
            f"{run.get('started_at', '')[:19]}"
        )
    print()


def _print_run_detail(run: dict) -> None:
    print(f"\n{'='*70}")
    print(f"站点:        {run.get('site')}")
    print(f"运行编号:    #{run.get('run_number'):05d}")
    print(f"状态:        {_status_color(run.get('status', '?'))}")
    print(f"URL:         {run.get('url')}")
    print(f"任务结果:    {run.get('mission_outcome')}")
    print(f"Trust score: {run.get('trust_score', 0):.2f}")
    print(f"事件数:      {run.get('events_collected', 0)}")
    print(f"开始时间:    {run.get('started_at', '')[:19]}")
    print(f"结束时间:    {run.get('finished_at', '')[:19]}")
    print(f"耗时:        {run.get('duration_sec', 0):.1f}s")
    if run.get("failure_category"):
        print(f"失败分类:    [{run['failure_category']}] {run.get('failure_detail', '')}")
    if run.get("error_message"):
        print(f"错误信息:    {run['error_message'][:200]}")
    print(f"\n产出目录:    {run.get('run_dir')}")
    screenshots = run.get("screenshots", [])
    if screenshots:
        print(f"\n截图 ({len(screenshots)}):")
        for s in screenshots:
            print(f"  {s}")
    artifacts = run.get("engine_artifacts", [])
    if artifacts:
        print(f"\nEngine 产出物 ({len(artifacts)}):")
        for a in artifacts[:20]:
            print(f"  {a}")
        if len(artifacts) > 20:
            print(f"  ... 共 {len(artifacts)} 个文件")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        show_summary()
    elif len(args) == 1:
        show_site(args[0])
    elif len(args) == 2:
        show_site(args[0], int(args[1]))
    else:
        print("用法: python scripts/inspect_test_runs.py [site_name] [run_number]")
