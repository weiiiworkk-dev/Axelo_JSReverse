from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import structlog

log = structlog.get_logger()

# DeepSeek 模型单价（USD / 1M tokens）
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-chat":      (0.27,  1.10),
    "deepseek-reasoner":  (0.55,  2.19),
}


@dataclass
class CostRecord:
    session_id: str
    started_at: datetime = field(default_factory=datetime.now)

    # Token 用量
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # 资源调用次数
    browser_sessions: int = 0
    node_calls: int = 0
    ai_calls: int = 0

    # 成本估算
    total_usd: float = 0.0

    # 运行路径与阶段级观测
    route_label: str = "full_ai_unknown_family"
    stage_metrics: dict[str, dict] = field(default_factory=dict)
    reuse_hits: list[str] = field(default_factory=list)

    # 调用明细
    calls: list[dict] = field(default_factory=list)

    def _ensure_stage(self, stage: str) -> dict:
        if not stage:
            stage = "unknown"
        metrics = self.stage_metrics.setdefault(
            stage,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "browser_sessions": 0,
                "node_calls": 0,
                "bundle_kb": 0,
                "duration_ms": 0,
                "status": "",
                "exit_reason": "",
            },
        )
        return metrics

    def add_ai_call(self, model: str, input_tok: int, output_tok: int, stage: str = "") -> None:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["deepseek-chat"])
        cost = (input_tok * pricing[0] + output_tok * pricing[1]) / 1_000_000

        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.total_tokens += input_tok + output_tok
        self.total_usd += cost
        self.ai_calls += 1

        metrics = self._ensure_stage(stage or "ai")
        metrics["input_tokens"] += input_tok
        metrics["output_tokens"] += output_tok
        metrics["cost_usd"] = round(metrics["cost_usd"] + cost, 6)

        self.calls.append({
            "type": "ai",
            "model": model,
            "stage": stage,
            "input": input_tok,
            "output": output_tok,
            "cost_usd": round(cost, 6),
        })
        log.debug("cost_ai_call", stage=stage, tokens=input_tok + output_tok, cost_usd=f"${cost:.4f}")

    def add_browser_session(self, stage: str = "") -> None:
        self.browser_sessions += 1
        self._ensure_stage(stage or "browser")["browser_sessions"] += 1

    def add_node_call(self, stage: str = "") -> None:
        self.node_calls += 1
        self._ensure_stage(stage or "node")["node_calls"] += 1

    def add_bundle_bytes(self, size_bytes: int, stage: str = "") -> None:
        if size_bytes <= 0:
            return
        self._ensure_stage(stage or "bundles")["bundle_kb"] += max(1, size_bytes // 1024)

    def set_stage_timing(self, stage: str, duration_ms: int, status: str = "", exit_reason: str = "") -> None:
        metrics = self._ensure_stage(stage)
        metrics["duration_ms"] = max(metrics.get("duration_ms", 0), duration_ms)
        if status:
            metrics["status"] = status
        if exit_reason:
            metrics["exit_reason"] = exit_reason

    def set_route(self, route_label: str) -> None:
        if route_label:
            self.route_label = route_label

    def add_reuse_hit(self, hit: str) -> None:
        if hit and hit not in self.reuse_hits:
            self.reuse_hits.append(hit)

    def stage_costs(self) -> dict[str, dict]:
        payload: dict[str, dict] = {}
        for stage, metrics in self.stage_metrics.items():
            payload[stage] = {
                "input_tokens": int(metrics.get("input_tokens", 0)),
                "output_tokens": int(metrics.get("output_tokens", 0)),
                "cost_usd": round(float(metrics.get("cost_usd", 0.0)), 6),
                "browser_sessions": int(metrics.get("browser_sessions", 0)),
                "node_calls": int(metrics.get("node_calls", 0)),
                "bundle_kb": int(metrics.get("bundle_kb", 0)),
                "duration_ms": int(metrics.get("duration_ms", 0)),
                "status": metrics.get("status", ""),
                "exit_reason": metrics.get("exit_reason", ""),
            }
        return payload

    def summary(self) -> str:
        return (
            f"总成本: ${self.total_usd:.4f} | "
            f"Token: {self.total_tokens:,} ({self.input_tokens:,}in / {self.output_tokens:,}out) | "
            f"AI调用: {self.ai_calls} | 浏览器: {self.browser_sessions} | Node: {self.node_calls} | "
            f"路径: {self.route_label}"
        )


class CostBudget:
    """
    预算控制：超出预算时降级到更便宜的模型或跳过非关键步骤。
    """

    def __init__(self, max_usd: float = 1.0, max_tokens: int = 500_000) -> None:
        self.max_usd = max_usd
        self.max_tokens = max_tokens

    def select_model(self, record: CostRecord, preferred: str) -> str:
        """根据剩余预算选择合适的模型"""
        remaining = self.max_usd - record.total_usd
        if remaining < 0.05:
            log.warning("budget_low_switch_chat", remaining=f"${remaining:.4f}")
            return "deepseek-chat"
        if remaining < 0.20 and preferred == "deepseek-reasoner":
            log.info("budget_medium_switch_chat", remaining=f"${remaining:.4f}")
            return "deepseek-chat"
        return preferred

    def should_skip_dynamic(self, record: CostRecord) -> bool:
        """预算不足时跳过高成本的动态分析"""
        return record.total_usd > self.max_usd * 0.6

    def should_skip_ai(self, record: CostRecord) -> bool:
        return record.total_usd > self.max_usd * 0.9
