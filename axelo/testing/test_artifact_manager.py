"""测试产出物管理器 — 按网站名称+编号目录保存每次测试运行的所有产出物。

目录结构:
    workspace/test_runs/
    ├── amazon/
    │   ├── 00001/          ← 第 1 次测试产出
    │   │   ├── test_report.json      ← 测试结论
    │   │   ├── session_id.txt        ← 对应的 engine session ID
    │   │   ├── screenshots/          ← Playwright 截图
    │   │   ├── network_har/          ← HAR 记录（如有）
    │   │   └── engine_artifacts/     ← 从 engine sessions/ 复制的产出物
    │   ├── 00002/
    │   └── ...
    ├── lazada/
    ├── ebay/
    ├── shopee/
    ├── temu/
    ├── jd/
    ├── taobao/
    └── pinduoduo/
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from axelo.config import settings


class TestArtifactManager:
    """管理单次网站测试运行的产出物目录。"""

    def __init__(self, site_name: str, workspace: Path | None = None) -> None:
        self.site_name = site_name.lower().strip()
        self._workspace = Path(workspace or settings.workspace)
        self._test_runs_root = self._workspace / "test_runs"
        self._site_dir = self._test_runs_root / self.site_name
        self._site_dir.mkdir(parents=True, exist_ok=True)

        # 分配编号目录
        self.run_number = self._next_run_number()
        self.run_dir = self._site_dir / f"{self.run_number:05d}"
        self.screenshots_dir = self.run_dir / "screenshots"
        self.network_har_dir = self.run_dir / "network_har"
        self.engine_artifacts_dir = self.run_dir / "engine_artifacts"

        for d in (self.run_dir, self.screenshots_dir, self.network_har_dir, self.engine_artifacts_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._start_time = datetime.utcnow()
        self._report: dict[str, Any] = {
            "site": self.site_name,
            "run_number": self.run_number,
            "run_dir": str(self.run_dir),
            "started_at": self._start_time.isoformat() + "Z",
            "finished_at": None,
            "status": "running",        # running | passed | failed | error
            "session_id": "",
            "url": "",
            "goal": "",
            "failure_category": "",     # INFRA | ENGINE | BROWSER | AI | ""
            "failure_detail": "",
            "screenshots": [],
            "engine_artifacts": [],
            "events_collected": 0,
            "mission_outcome": "",
            "trust_score": 0.0,
            "error_message": "",
        }

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def set_session_id(self, session_id: str) -> None:
        self._report["session_id"] = session_id
        (self.run_dir / "session_id.txt").write_text(session_id, encoding="utf-8")

    def set_url_goal(self, url: str, goal: str) -> None:
        self._report["url"] = url
        self._report["goal"] = goal

    def record_screenshot(self, filename: str) -> Path:
        """返回截图保存路径并记录到报告。"""
        path = self.screenshots_dir / filename
        self._report["screenshots"].append(str(path))
        return path

    def copy_engine_artifacts(self, engine_session_dir: Path) -> int:
        """从 engine session 目录复制产出物，返回复制的文件数量。"""
        if not engine_session_dir.exists():
            return 0
        count = 0
        for src in engine_session_dir.rglob("*"):
            if src.is_file():
                rel = src.relative_to(engine_session_dir)
                dst = self.engine_artifacts_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                self._report["engine_artifacts"].append(str(dst))
                count += 1
        return count

    def finalize(
        self,
        *,
        status: str,
        failure_category: str = "",
        failure_detail: str = "",
        events_collected: int = 0,
        mission_outcome: str = "",
        trust_score: float = 0.0,
        error_message: str = "",
    ) -> Path:
        """写入最终报告，返回报告文件路径。"""
        self._report.update(
            {
                "finished_at": datetime.utcnow().isoformat() + "Z",
                "status": status,
                "failure_category": failure_category,
                "failure_detail": failure_detail,
                "events_collected": events_collected,
                "mission_outcome": mission_outcome,
                "trust_score": trust_score,
                "error_message": error_message,
                "duration_sec": (datetime.utcnow() - self._start_time).total_seconds(),
            }
        )
        report_path = self.run_dir / "test_report.json"
        report_path.write_text(
            json.dumps(self._report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report_path

    # ──────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────

    def _next_run_number(self) -> int:
        """扫描现有编号目录，返回下一个可用编号（从 1 开始）。"""
        existing = sorted(
            int(d.name) for d in self._site_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )
        return (existing[-1] + 1) if existing else 1


def list_test_runs(site_name: str, workspace: Path | None = None) -> list[dict[str, Any]]:
    """列出指定站点所有测试运行的报告。"""
    ws = Path(workspace or settings.workspace)
    site_dir = ws / "test_runs" / site_name.lower()
    if not site_dir.exists():
        return []
    runs = []
    for run_dir in sorted(site_dir.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.isdigit():
            continue
        report_path = run_dir / "test_report.json"
        if report_path.exists():
            try:
                runs.append(json.loads(report_path.read_text(encoding="utf-8")))
            except Exception:
                runs.append({"run_dir": str(run_dir), "status": "unreadable"})
    return runs


def summarize_all_runs(workspace: Path | None = None) -> dict[str, Any]:
    """汇总所有站点的测试结果。"""
    ws = Path(workspace or settings.workspace)
    test_runs_root = ws / "test_runs"
    if not test_runs_root.exists():
        return {}
    summary: dict[str, Any] = {}
    for site_dir in sorted(test_runs_root.iterdir()):
        if not site_dir.is_dir():
            continue
        runs = list_test_runs(site_dir.name, workspace)
        if runs:
            latest = runs[-1]
            summary[site_dir.name] = {
                "total_runs": len(runs),
                "latest_status": latest.get("status"),
                "latest_run": latest.get("run_number"),
                "latest_outcome": latest.get("mission_outcome"),
                "latest_trust": latest.get("trust_score"),
            }
    return summary
