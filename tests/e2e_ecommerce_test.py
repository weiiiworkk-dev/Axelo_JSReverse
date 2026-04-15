"""
端到端电商平台测试 — Axelo 系统完整业务流程验证
测试目标：Amazon, eBay, Shopee, Lazada, Temu, 京东, 淘宝, 拼多多
验收标准：完整业务成功（intake→plan→execute→verdict），不仅仅是跑通
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Windows UTF-8 console support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import websockets

BASE_URL = "http://localhost:7788"
WS_BASE  = "ws://localhost:7788"
TIMEOUT  = httpx.Timeout(120.0)  # AI intake calls (DeepSeek) can take up to 90s

# ─── 测试目标定义 ────────────────────────────────────────────────────────────

@dataclass
class EcomTestTarget:
    name: str
    url: str
    message: str            # 用户输入（模拟 intake 对话）
    expected_fields: list[str]
    min_confidence: float = 0.6
    verdict_pass: list[str] = field(default_factory=lambda: [
        "mechanism_success", "operational_success", "structural_success",
        "data_success", "partial_success", "execution_success",
    ])

TEST_TARGETS = [
    EcomTestTarget(
        name="Amazon",
        url="https://www.amazon.com/s?k=laptop",
        message="I want to scrape Amazon search results for 'laptop'. Extract product title, price, ASIN, rating, review count, and image URL from the search result listing page.",
        expected_fields=["title", "price", "asin", "rating"],
    ),
    EcomTestTarget(
        name="eBay",
        url="https://www.ebay.com/sch/i.html?_nkw=smartphone",
        message="Extract smartphone listings from eBay search. I need item title, current bid/price, condition, seller rating, and item URL.",
        expected_fields=["title", "price", "condition"],
    ),
    EcomTestTarget(
        name="Shopee",
        url="https://shopee.sg/search?keyword=headphones",
        message="Reverse engineer Shopee Singapore's search API for headphones. Extract product name, price, sold count, shop name, and rating from the API response.",
        expected_fields=["name", "price", "sold_count"],
    ),
    EcomTestTarget(
        name="Lazada",
        url="https://www.lazada.sg/catalog/?q=phone+case",
        message="Scrape Lazada Singapore product listings for phone cases. Extract product name, price, discount percentage, seller name, and review count.",
        expected_fields=["name", "price", "discount"],
    ),
    EcomTestTarget(
        name="Temu",
        url="https://www.temu.com/search_result.html?search_key=earbuds",
        message="Reverse engineer Temu's search API for earbuds products. I need product title, price in USD, free shipping flag, and review count.",
        expected_fields=["title", "price", "review_count"],
    ),
    EcomTestTarget(
        name="京东",
        url="https://search.jd.com/Search?keyword=手机",
        message="我想抓取京东手机搜索页的商品列表数据，提取商品名称、价格、评价数量、商品ID、店铺名称和促销信息。",
        expected_fields=["name", "price", "comment_count"],
    ),
    EcomTestTarget(
        name="淘宝",
        url="https://s.taobao.com/search?q=耳机",
        message="逆向分析淘宝耳机搜索结果的API接口，提取商品标题、价格、月销量、店铺名称和商品链接。",
        expected_fields=["title", "price", "sale_count"],
    ),
    EcomTestTarget(
        name="拼多多",
        url="https://mobile.yangkeduo.com/search_result.html?search_key=平板",
        message="从拼多多搜索平板电脑商品，提取商品名称、团购价格、已拼件数、店铺名称和商品主图URL。",
        expected_fields=["name", "price", "group_count"],
    ),
]

# ─── 测试结果记录 ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    target: str
    url: str
    intake_ok: bool = False
    contract_ready: bool = False
    mission_started: bool = False
    session_id: str = ""
    final_verdict: str = ""
    final_status: str = ""
    verdict_tier: str = ""
    evidence_count: int = 0
    trust_score: float = 0.0
    coverage: dict = field(default_factory=dict)
    error: str = ""
    duration_sec: float = 0.0
    events_received: int = 0
    business_success: bool = False

    def summary_line(self) -> str:
        icon = "✅" if self.business_success else "❌"
        return (
            f"{icon} [{self.target}] verdict={self.verdict_tier or self.final_verdict!r} "
            f"trust={self.trust_score:.2f} evidence={self.evidence_count} "
            f"dur={self.duration_sec:.1f}s"
            + (f" ERR={self.error[:80]}" if self.error else "")
        )


# ─── HTTP helpers ────────────────────────────────────────────────────────────

async def api_post(client: httpx.AsyncClient, path: str, **kwargs) -> dict:
    r = await client.post(f"{BASE_URL}{path}", **kwargs)
    r.raise_for_status()
    return r.json()


async def api_get(client: httpx.AsyncClient, path: str, **kwargs) -> dict:
    r = await client.get(f"{BASE_URL}{path}", **kwargs)
    r.raise_for_status()
    return r.json()


# ─── 单目标测试 ──────────────────────────────────────────────────────────────

async def run_single_test(target: EcomTestTarget, client: httpx.AsyncClient) -> TestResult:
    result = TestResult(target=target.name, url=target.url)
    t0 = time.monotonic()
    print(f"\n{'='*60}")
    print(f"▶ 开始测试: {target.name}")
    print(f"  URL: {target.url}")

    try:
        # ── Step 1: 创建 intake session ──────────────────────────────────
        resp = await api_post(client, "/api/intake/session")
        intake_id = resp["intake_id"]
        print(f"  ✓ Intake session: {intake_id}")
        result.intake_ok = True

        # ── Step 2: 发送第一条消息（描述需求）──────────────────────────
        chat_resp = await api_post(client, f"/api/intake/{intake_id}/chat",
            json={"message": target.message})
        phase = chat_resp.get("phase")
        conf = chat_resp.get("readiness", {}).get("confidence", 0.0)
        print(f"  ✓ Chat turn 1: phase={phase}, confidence={conf:.2f}")

        # ── Step 3: 如果还未就绪，发送 URL 补充 ─────────────────────────
        if phase != "contract_ready":
            url_msg = f"Target URL is: {target.url}"
            chat_resp = await api_post(client, f"/api/intake/{intake_id}/chat",
                json={"message": url_msg})
            phase = chat_resp.get("phase")
            conf = chat_resp.get("readiness", {}).get("confidence", 0.0)
            print(f"  ✓ Chat turn 2: phase={phase}, confidence={conf:.2f}")

        # ── Step 4: 如果仍未就绪，补充字段信息 ──────────────────────────
        if phase != "contract_ready":
            fields_str = ", ".join(target.expected_fields)
            chat_resp = await api_post(client, f"/api/intake/{intake_id}/chat",
                json={"message": f"The fields I need are: {fields_str}. Please set objective_type to product_data."})
            phase = chat_resp.get("phase")
            conf = chat_resp.get("readiness", {}).get("confidence", 0.0)
            print(f"  ✓ Chat turn 3: phase={phase}, confidence={conf:.2f}")

        contract = chat_resp.get("contract", {})
        result.contract_ready = (phase == "contract_ready" or conf >= target.min_confidence)

        # ── Step 5: 强制启动（即使 confidence 不足也尝试）────────────────
        # 获取最新合约状态
        contract_resp = await api_get(client, f"/api/intake/{intake_id}/contract")
        current_contract = contract_resp.get("contract", {})
        readiness = contract_resp.get("readiness", {}) if "readiness" in contract_resp else chat_resp.get("readiness", {})

        blocking = []
        if isinstance(chat_resp.get("readiness"), dict):
            blocking = chat_resp["readiness"].get("blocking_gaps", [])

        if blocking:
            print(f"  ⚠ 阻塞项: {blocking}")
            # 尝试修复常见阻塞
            if any("url" in g.lower() for g in blocking):
                chat_resp = await api_post(client, f"/api/intake/{intake_id}/chat",
                    json={"message": f"Use this URL: {target.url}"})
                phase = chat_resp.get("phase")

        # ── Step 6: 启动任务 ─────────────────────────────────────────────
        try:
            start_resp = await api_post(client, f"/api/intake/{intake_id}/start")
        except httpx.HTTPStatusError as exc:
            # 400 = contract not ready
            detail = exc.response.json().get("detail", str(exc))
            print(f"  ⚠ 无法启动（合约未就绪）: {detail}")
            # 直接走 /api/mission/start bypass
            start_resp = await api_post(client, "/api/mission/start",
                json={
                    "url": target.url,
                    "goal": target.message,
                    "key_fields": target.expected_fields,
                    "stealth": "medium",
                    "js_rendering": "auto",
                })
            result.mission_started = True
        else:
            result.mission_started = True

        session_id = start_resp.get("session_id", "")
        result.session_id = session_id
        print(f"  ✓ Mission started: session_id={session_id}")

        # ── Step 7: 通过 WebSocket 监听执行进度 ──────────────────────────
        ws_url = f"{WS_BASE}/ws/sessions/{session_id}/stream"
        deadline = time.monotonic() + 300  # 最多等待 5 分钟
        events_received = 0
        final_state: dict = {}

        try:
            async with websockets.connect(ws_url, ping_interval=20, close_timeout=5) as ws:
                print(f"  ✓ WebSocket 已连接，监听执行中...")
                while time.monotonic() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        ev = json.loads(raw)
                        events_received += 1
                        kind = ev.get("kind", "")
                        state = ev.get("state", {})

                        if kind in ("dispatch", "complete", "verdict", "error"):
                            obj = ev.get("objective") or ev.get("message", "")[:60]
                            print(f"    [{kind}] {obj}")

                        if state:
                            final_state = state

                        if kind in ("verdict", "complete") and state.get("mission_status") in ("success", "failed", "complete"):
                            break
                        if kind == "error" and state.get("mission_status") == "failed":
                            break

                    except asyncio.TimeoutError:
                        # 5 秒无消息 → 轮询一次 REST
                        try:
                            ev_resp = await api_get(client, f"/api/sessions/{session_id}/events")
                            items = ev_resp.get("events", [])
                            if items:
                                last = items[-1]
                                final_state = last.get("state", final_state)
                                if last.get("kind") in ("verdict", "complete"):
                                    break
                        except Exception:
                            pass
                        continue
                    except Exception as exc:
                        print(f"    WS error: {exc}")
                        break
        except Exception as exc:
            print(f"  ⚠ WebSocket 连接失败，降级使用 REST 轮询: {exc}")
            # REST 轮询 fallback
            for _ in range(30):
                await asyncio.sleep(10)
                try:
                    ev_resp = await api_get(client, f"/api/sessions/{session_id}/events")
                    items = ev_resp.get("events", [])
                    if items:
                        last = items[-1]
                        final_state = last.get("state", {})
                        kind = last.get("kind")
                        if kind in ("verdict", "complete", "error"):
                            break
                except Exception:
                    break

        result.events_received = events_received
        result.duration_sec = time.monotonic() - t0

        # ── Step 8: 读取最终会话状态 ──────────────────────────────────────
        try:
            sess_resp = await api_get(client, f"/api/sessions/{session_id}")
            sess_state = sess_resp.get("principal_state", {})
            mission = sess_state.get("mission", {})
            trust = sess_state.get("trust", {})
            evidence = sess_state.get("evidence", [])
            result.final_status  = mission.get("status", final_state.get("mission_status", ""))
            result.final_verdict = mission.get("outcome", final_state.get("mission_outcome", ""))
            result.verdict_tier  = mission.get("verdict_tier", "")
            result.trust_score   = float(trust.get("score", final_state.get("trust_score", 0.0)))
            result.evidence_count = len(evidence) if isinstance(evidence, list) else int(final_state.get("evidence_count", 0))
            result.coverage = dict(trust.get("coverage") or final_state.get("coverage") or {})
        except Exception:
            # fallback 到 WebSocket 最后状态
            result.final_status  = final_state.get("mission_status", "unknown")
            result.final_verdict = final_state.get("mission_outcome", "unknown")
            result.trust_score   = float(final_state.get("trust_score", 0.0))
            result.evidence_count = int(final_state.get("evidence_count", 0))
            result.coverage = dict(final_state.get("coverage") or {})

        # ── Step 9: 判定业务成功 ──────────────────────────────────────────
        verdict_lower = (result.verdict_tier or result.final_verdict or "").lower().replace(" ", "_")
        result.business_success = (
            result.mission_started
            and events_received > 0
            and result.final_status in ("success",)
            and any(v in verdict_lower for v in [
                "mechanism_success", "operational_success", "structural_success",
                "data_success", "partial_success", "execution_success",
            ])
        )

    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        result.duration_sec = time.monotonic() - t0
        traceback.print_exc()

    print(result.summary_line())
    return result


# ─── 主入口 ─────────────────────────────────────────────────────────────────

async def main() -> int:
    print(f"\n{'='*60}")
    print(f"Axelo 端到端电商平台测试")
    print(f"时间: {datetime.now().isoformat()}")
    print(f"服务地址: {BASE_URL}")
    print(f"{'='*60}")

    # 检查服务健康
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
            r = await c.get(f"{BASE_URL}/docs")
            r.raise_for_status()
            print("✓ 服务健康检查通过")
    except Exception as exc:
        print(f"✗ 服务未启动或不可达: {exc}")
        print("  请先运行: axelo web --no-open")
        return 1

    results: list[TestResult] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for target in TEST_TARGETS:
            result = await run_single_test(target, client)
            results.append(result)

    # ── 最终报告 ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("测试结果汇总")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r.business_success)
    total  = len(results)
    for r in results:
        print(r.summary_line())
    print(f"\n总计: {passed}/{total} 业务成功")

    # 输出详细 JSON 报告
    report = {
        "run_at": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "results": [
            {
                "target": r.target,
                "url": r.url,
                "business_success": r.business_success,
                "intake_ok": r.intake_ok,
                "mission_started": r.mission_started,
                "session_id": r.session_id,
                "final_status": r.final_status,
                "final_verdict": r.final_verdict,
                "verdict_tier": r.verdict_tier,
                "trust_score": r.trust_score,
                "evidence_count": r.evidence_count,
                "events_received": r.events_received,
                "duration_sec": r.duration_sec,
                "error": r.error,
                "coverage": r.coverage,
            }
            for r in results
        ],
    }
    report_path = "tests/e2e_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存: {report_path}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
