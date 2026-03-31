from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import structlog

log = structlog.get_logger()

# Claude 模型单价（USD / 1M tokens）
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6":    (15.0,  75.0),   # input, output
    "claude-sonnet-4-6":  (3.0,   15.0),
    "claude-haiku-4-5":   (0.25,   1.25),
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

    # 调用明细
    calls: list[dict] = field(default_factory=list)

    def add_ai_call(self, model: str, input_tok: int, output_tok: int, stage: str = "") -> None:
        pricing = MODEL_PRICING.get(model, (15.0, 75.0))
        cost = (input_tok * pricing[0] + output_tok * pricing[1]) / 1_000_000

        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.total_tokens += input_tok + output_tok
        self.total_usd += cost
        self.ai_calls += 1

        self.calls.append({
            "type": "ai",
            "model": model,
            "stage": stage,
            "input": input_tok,
            "output": output_tok,
            "cost_usd": round(cost, 6),
        })
        log.debug("cost_ai_call", stage=stage, tokens=input_tok + output_tok, cost_usd=f"${cost:.4f}")

    def add_browser_session(self) -> None:
        self.browser_sessions += 1

    def add_node_call(self) -> None:
        self.node_calls += 1

    def summary(self) -> str:
        return (
            f"总成本: ${self.total_usd:.4f} | "
            f"Token: {self.total_tokens:,} ({self.input_tokens:,}in / {self.output_tokens:,}out) | "
            f"AI调用: {self.ai_calls} | 浏览器: {self.browser_sessions} | Node: {self.node_calls}"
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
            log.warning("budget_low_switch_haiku", remaining=f"${remaining:.4f}")
            return "claude-haiku-4-5"
        if remaining < 0.20 and "opus" in preferred:
            log.info("budget_medium_switch_sonnet", remaining=f"${remaining:.4f}")
            return "claude-sonnet-4-6"
        return preferred

    def should_skip_dynamic(self, record: CostRecord) -> bool:
        """预算不足时跳过高成本的动态分析"""
        return record.total_usd > self.max_usd * 0.6

    def should_skip_ai(self, record: CostRecord) -> bool:
        return record.total_usd > self.max_usd * 0.9
