from __future__ import annotations
from abc import ABC, abstractmethod
from axelo.models.pipeline import Decision, PipelineState


class ModeController(ABC):
    """
    所有人工决策门控的唯一抽象。
    流水线各阶段只调用 gate()，不感知具体模式。
    """
    name: str

    @abstractmethod
    async def gate(self, decision: Decision, state: PipelineState) -> str:
        """
        返回决策结果字符串（对应 decision.options 中的某项，或自由文本）。
        - interactive: 展示 Rich UI，等待键盘输入
        - auto:        使用 decision.default，记录日志
        - manual:      阻塞直到人工输入 run 指令
        """
        ...

    @abstractmethod
    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        """
        是否跳过该阶段的 gate 调用（极高置信度场景）。
        auto 模式始终返回 True，interactive 模式在置信度 > 阈值时返回 True。
        """
        ...
