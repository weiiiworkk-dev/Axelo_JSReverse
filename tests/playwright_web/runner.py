"""核心测试执行器 — 单次网站测试的完整流程（同步 Playwright API）。

流程:
1. 打开 Web UI → 截图初始状态
2. 通过 Playwright request API 提交任务（POST /api/mission/start）
3. 轮询 GET /api/sessions/{session_id}/events，直到任务完成
4. 期间每 30 秒截图一次
5. 任务完成后截图最终状态
6. 收集 engine artifacts，写入测试产出物目录
7. 写入 test_report.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import Page

from axelo.config import settings
from axelo.testing.test_artifact_manager import TestArtifactManager
from tests.playwright_web.sites import SiteConfig

# 任务最大等待时间（秒）
MISSION_TIMEOUT_SEC = 600   # 10 分钟
# 事件轮询间隔（秒）
POLL_INTERVAL_SEC = 5
# 定期截图间隔（秒）
SCREENSHOT_INTERVAL_SEC = 30


def run_site_test(page: Page, site: SiteConfig, base_url: str) -> dict[str, Any]:
    """
    执行单个站点的完整测试（同步版本）。

    返回: test_report.json 的内容字典
    """
    tam = TestArtifactManager(site.name)
    tam.set_url_goal(site.url, site.goal)

    # ── 步骤 1: 打开 Web UI ────────────────────────────────────
    try:
        page.goto(base_url, timeout=30_000, wait_until="domcontentloaded")
        time.sleep(1)
        screenshot_path = tam.record_screenshot("01_web_ui_initial.png")
        page.screenshot(path=str(screenshot_path), full_page=False)
    except Exception as exc:
        report_path = tam.finalize(
            status="error",
            failure_category="INFRA",
            failure_detail="Web UI failed to load",
            error_message=str(exc),
        )
        return json.loads(report_path.read_text(encoding="utf-8"))

    # ── 步骤 2: 通过 API 提交任务 ──────────────────────────────
    session_id = ""
    try:
        payload = {
            "url": site.url,
            "goal": site.goal,
            "stealth": site.stealth,
            "js_rendering": site.js_rendering,
            "verify": site.verify,
            "data_type": "product_data",
            "budget_usd": 3.0,
            "time_limit_min": 10,
        }
        resp = page.request.post(
            f"{base_url}/api/mission/start",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=30_000,
        )
        if not resp.ok:
            body = resp.text()
            report_path = tam.finalize(
                status="error",
                failure_category="INFRA",
                failure_detail=f"POST /api/mission/start returned HTTP {resp.status}",
                error_message=body,
            )
            return json.loads(report_path.read_text(encoding="utf-8"))

        result = resp.json()
        session_id = result.get("session_id", "")
        if not session_id:
            report_path = tam.finalize(
                status="error",
                failure_category="INFRA",
                failure_detail="No session_id in mission start response",
                error_message=json.dumps(result),
            )
            return json.loads(report_path.read_text(encoding="utf-8"))

        tam.set_session_id(session_id)

        # 截图：任务已提交
        screenshot_path = tam.record_screenshot("02_mission_started.png")
        page.screenshot(path=str(screenshot_path), full_page=False)

    except Exception as exc:
        report_path = tam.finalize(
            status="error",
            failure_category="INFRA",
            failure_detail="Exception during mission start",
            error_message=str(exc),
        )
        return json.loads(report_path.read_text(encoding="utf-8"))

    # ── 步骤 3: 轮询事件直到完成 ──────────────────────────────
    events_url = f"{base_url}/api/sessions/{session_id}/events"
    mission_status = "running"
    mission_outcome = ""
    trust_score = 0.0
    events_collected = 0
    failure_category = ""
    failure_detail = ""
    error_message = ""
    last_screenshot_time = time.time()
    deadline = time.time() + MISSION_TIMEOUT_SEC
    since_line = 0

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SEC)

        # 定期截图
        if time.time() - last_screenshot_time >= SCREENSHOT_INTERVAL_SEC:
            try:
                idx = len(tam._report["screenshots"]) + 1
                sp = tam.record_screenshot(f"{idx:02d}_progress.png")
                page.screenshot(path=str(sp), full_page=False)
                last_screenshot_time = time.time()
            except Exception:
                pass

        # 获取新事件
        try:
            r = httpx.get(events_url, params={"since_line": since_line}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                new_events: list[dict] = data.get("events", [])
                since_line = data.get("next_line", since_line)
                events_collected += len(new_events)

                for event in new_events:
                    state = (
                        event.get("data", {}).get("state")
                        or event.get("state")
                        or {}
                    )
                    status_in_event = (
                        state.get("mission_status")
                        or event.get("data", {}).get("mission_status")
                    )
                    if status_in_event in ("completed", "failed", "cancelled"):
                        mission_status = status_in_event
                        mission_outcome = str(state.get("mission_outcome") or "")
                        trust_info = state.get("trust") or {}
                        trust_score = float(trust_info.get("score", 0.0))
                        break

                if mission_status in ("completed", "failed", "cancelled"):
                    break
        except Exception:
            pass  # 网络抖动，继续轮询

    # ── 步骤 4: 补充最终会话详情 ──────────────────────────────
    try:
        r2 = httpx.get(f"{base_url}/api/sessions/{session_id}", timeout=15)
        if r2.status_code == 200:
            detail = r2.json()
            mission_report = detail.get("mission_report") or {}
            if trust_score == 0.0:
                trust_info = mission_report.get("trust") or {}
                trust_score = float(trust_info.get("score", 0.0))
            if not mission_outcome:
                mission_outcome = str(mission_report.get("mission_outcome") or "")
            if not mission_status or mission_status == "running":
                mission_status = str(mission_report.get("mission_status") or "unknown")
    except Exception:
        pass

    # ── 步骤 5: 截图最终状态 ──────────────────────────────────
    try:
        sp = tam.record_screenshot("99_final_state.png")
        page.screenshot(path=str(sp), full_page=False)
    except Exception:
        pass

    # ── 步骤 6: 复制 engine artifacts ─────────────────────────
    engine_session_dir = _find_engine_session_dir(session_id)
    if engine_session_dir:
        tam.copy_engine_artifacts(engine_session_dir)

    # ── 步骤 7: 判断失败类型 ──────────────────────────────────
    final_status = "passed"
    if mission_status == "running":
        final_status = "failed"
        failure_category = "ENGINE"
        failure_detail = (
            f"Mission timed out after {MISSION_TIMEOUT_SEC}s without completion signal"
        )
    elif mission_status in ("failed", "cancelled"):
        final_status = "failed"
        failure_category = _classify_failure(mission_outcome, error_message)
        failure_detail = mission_outcome or error_message

    report_path = tam.finalize(
        status=final_status,
        failure_category=failure_category,
        failure_detail=failure_detail,
        events_collected=events_collected,
        mission_outcome=mission_outcome,
        trust_score=trust_score,
        error_message=error_message,
    )
    return json.loads(report_path.read_text(encoding="utf-8"))


def _find_engine_session_dir(session_id: str) -> Path | None:
    """在 workspace/sessions/ 下递归查找匹配 session_id 的目录。"""
    sessions_root = settings.sessions_dir
    if not sessions_root.exists():
        return None
    for site_dir in sessions_root.iterdir():
        if not site_dir.is_dir():
            continue
        candidate = site_dir / session_id
        if candidate.is_dir():
            return candidate
    return None


def _classify_failure(outcome: str, error: str) -> str:
    """根据任务结果文本，分类失败根因。"""
    combined = (outcome + " " + error).lower()
    if any(k in combined for k in ("429", "403", "captcha", "blocked", "anti_bot", "challenge", "rate_limit")):
        return "BROWSER"
    if any(k in combined for k in ("codegen", "ai", "deepseek", "api_key", "llm", "generate")):
        return "AI"
    if any(k in combined for k in ("connection", "timeout", "network", "502", "503", "socket")):
        return "INFRA"
    return "ENGINE"
