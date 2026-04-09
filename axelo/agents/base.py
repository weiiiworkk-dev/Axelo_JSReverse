from __future__ import annotations
from abc import ABC, abstractmethod
from pydantic import BaseModel
from axelo.ai.client import AIClient
from axelo.cost.tracker import CostRecord, CostBudget


class BaseAgent(ABC):
    """
    所有 AI 角色的基类。
    每个角色有固定的职责、系统 prompt 和输出格式。
    通过 CostRecord 追踪每次调用的 token 用量。
    """

    role: str = ""          # 角色名（用于日志和成本追踪）
    default_model: str = "deepseek-chat"

    def __init__(
        self,
        client: AIClient,
        cost: CostRecord,
        budget: CostBudget,
    ) -> None:
        self._client = client
        self._cost = cost
        self._budget = budget

    def _select_model(self) -> str:
        """根据预算选择模型"""
        return self._budget.select_model(self._cost, self.default_model)

    def _build_client(self) -> AIClient:
        """返回配置了适当模型的 client"""
        self._client._model = self._select_model()
        return self._client
