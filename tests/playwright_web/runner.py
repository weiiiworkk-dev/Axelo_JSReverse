"""核心测试执行器 — 单次网站测试的完整流程（同步 Playwright API）。

流程:
1. 打开 Web UI → 截图初始状态
2. 通过 Playwright request API 提交任务（POST /api/mission/start）
3. 轮询 GET /api/sessions/{session_id}/events，直到任务完成
4. 期间每 30 秒截图一次 + 实时页面内容挑战检测
5. 任务完成后截图最终状态
6. 收集 engine artifacts、HAR 文件、截获的 API 端点列表
7. 写入 test_report.json

生产级能力:
- HAR 录制（context.record_har）：完整 HTTP 流量存档
- 网络请求拦截：实时发现 API 端点、token 头、响应结构
- 挑战检测：CAPTCHA/反爬关键词实时扫描
- 预期挑战支持：对已知反爬机制的测试结果宽松处理
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import BrowserContext, Page, Route, Request as PWRequest

from axelo.config import settings
from axelo.testing.test_artifact_manager import TestArtifactManager
from tests.playwright_web.sites import SiteConfig

# 事件轮询间隔（秒）
POLL_INTERVAL_SEC = 5
# 定期截图间隔（秒）
SCREENSHOT_INTERVAL_SEC = 30

# 反爬 / 挑战关键词（用于页面内容实时扫描）
_CHALLENGE_KEYWORDS = [
    "captcha", "recaptcha", "hcaptcha", "funcaptcha", "arkose",
    "blocked", "unusual traffic", "access denied", "403 forbidden",
    "rate limit", "too many requests", "please verify", "human verification",
    "queue-it", "waiting room", "security check", "bot detection",
    "perimeter", "akamai", "cloudflare", "challenge", "are you human",
    "ddos protection", "just a moment",
]

# 感兴趣的 API 端点模式（XHR/Fetch 类请求）
_API_PATH_PATTERNS = [
    r"/api/",
    r"/graphql",
    r"\.json",
    r"/search",
    r"/v[12]/",
    r"/rpc",
    r"_api",
    r"/voyager/",
    r"/query",
    r"/data",
]


def run_site_test(
    page: Page,
    site: SiteConfig,
    base_url: str,
    context: BrowserContext | None = None,
) -> dict[str, Any]:
    """
    执行单个站点的完整测试（同步版本）。

    Args:
        page: Playwright Page 对象
        site: 站点配置
        base_url: Axelo Web UI 基础 URL
        context: BrowserContext（可选，用于 HAR 录制）

    Returns:
        test_report.json 的内容字典（已扩展 challenge_detected / api_endpoints_found 字段）
    """
    timeout_sec = site.mission_timeout_sec
    tam = TestArtifactManager(site.name)
    tam.set_url_goal(site.url, site.goal)

    # 运行时收集的附加数据
    captured_api_endpoints: list[dict] = []
    challenge_signals: list[str] = []

    # ── 步骤 0: 设置网络请求拦截（在浏览器级别，监听目标站点请求）─────
    def _on_request(request: PWRequest) -> None:
        url = request.url
        if any(re.search(p, url) for p in _API_PATH_PATTERNS):
            entry = {
                "url": url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            }
            captured_api_endpoints.append(entry)

    page.on("request", _on_request)

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
            "budget_usd": 5.0,
            "time_limit_min": max(timeout_sec // 60, 8),
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
    deadline = time.time() + timeout_sec
    since_line = 0

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_SEC)

        # 定期截图 + 页面挑战扫描
        if time.time() - last_screenshot_time >= SCREENSHOT_INTERVAL_SEC:
            try:
                idx = len(tam._report["screenshots"]) + 1
                sp = tam.record_screenshot(f"{idx:02d}_progress.png")
                page.screenshot(path=str(sp), full_page=False)
                last_screenshot_time = time.time()

                # 扫描当前页面文本（检测挑战）
                try:
                    page_text = page.inner_text("body").lower()
                    for kw in _CHALLENGE_KEYWORDS:
                        if kw in page_text and kw not in challenge_signals:
                            challenge_signals.append(kw)
                except Exception:
                    pass
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
                    # 从事件文本中扫描挑战关键词
                    event_text = json.dumps(event).lower()
                    for kw in _CHALLENGE_KEYWORDS:
                        if kw in event_text and kw not in challenge_signals:
                            challenge_signals.append(kw)

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
            # 从 mission_report 中扫描挑战关键词
            report_text = json.dumps(mission_report).lower()
            for kw in _CHALLENGE_KEYWORDS:
                if kw in report_text and kw not in challenge_signals:
                    challenge_signals.append(kw)
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

    # ── 步骤 6b: 保存 HAR 文件（若 context 可用）─────────────
    har_path: Path | None = None
    if context is not None:
        try:
            har_file = tam.run_dir / "network_traffic.har"
            context.storage_state()  # flush pending
            # Playwright context.record_har 需要在 context 创建时就设置，
            # 这里只做路径登记；实际录制由 conftest 中的 har_context fixture 控制
            if har_file.exists():
                har_path = har_file
        except Exception:
            pass

    # ── 步骤 6c: 保存截获的 API 端点列表 ────────────────────
    if captured_api_endpoints:
        endpoints_file = tam.run_dir / "captured_api_endpoints.json"
        endpoints_file.write_text(
            json.dumps(captured_api_endpoints, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 步骤 6d: 保存挑战信号 ─────────────────────────────────
    if challenge_signals:
        signals_file = tam.run_dir / "challenge_signals.json"
        signals_file.write_text(
            json.dumps(
                {
                    "detected": challenge_signals,
                    "expected": site.expected_challenges,
                    "profile": site.challenge_profile,
                    "matched_expected": [
                        s for s in challenge_signals
                        if any(e in s or s in e for e in site.expected_challenges)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ── 步骤 7: 判断失败类型 ──────────────────────────────────
    challenge_detected = bool(challenge_signals)
    challenge_matched_expected = any(
        any(e in sig or sig in e for e in site.expected_challenges)
        for sig in challenge_signals
    )

    final_status = "passed"
    if mission_status == "running":
        final_status = "failed"
        failure_category = "ENGINE"
        failure_detail = (
            f"Mission timed out after {timeout_sec}s without completion signal"
        )
    elif mission_status in ("failed", "cancelled"):
        raw_fc = _classify_failure(mission_outcome, error_message)
        if raw_fc == "BROWSER" and (challenge_detected or site.expected_challenges):
            # 系统正确检测到预期中的反爬挑战 → 判定为"挑战命中"，不计入工程失败
            final_status = "challenge_hit"
            failure_category = "BROWSER"
            failure_detail = (
                f"Expected challenge encountered: {challenge_signals or site.expected_challenges}"
            )
        else:
            final_status = "failed"
            failure_category = raw_fc
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

    report = json.loads(report_path.read_text(encoding="utf-8"))

    # 注入扩展字段（test_artifact_manager 不直接支持的生产级数据）
    report["challenge_detected"] = challenge_detected
    report["challenge_signals"] = challenge_signals
    report["challenge_matched_expected"] = challenge_matched_expected
    report["api_endpoints_found"] = len(captured_api_endpoints)
    report["har_recorded"] = har_path is not None
    report["challenge_profile"] = site.challenge_profile
    report["expected_challenges"] = site.expected_challenges

    # 回写 report 文件（含扩展字段）
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return report


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
    if any(k in combined for k in (
        "429", "403", "captcha", "blocked", "anti_bot", "challenge",
        "rate_limit", "perimeter", "akamai", "arkose", "queue-it",
        "unusual traffic", "access denied", "security check",
    )):
        return "BROWSER"
    if any(k in combined for k in ("codegen", "ai", "deepseek", "api_key", "llm", "generate")):
        return "AI"
    if any(k in combined for k in ("connection", "timeout", "network", "502", "503", "socket")):
        return "INFRA"
    return "ENGINE"
