from __future__ import annotations
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
import uuid


class DecisionType(str, Enum):
    APPROVE_STAGE = "approve_stage"         # 直接批准当前阶段继续
    SELECT_OPTION = "select_option"         # 从多个选项中选择
    EDIT_ARTIFACT = "edit_artifact"         # 审查并可选编辑某个产物文件
    OVERRIDE_HYPOTHESIS = "override_hypothesis"  # 修改AI的分析假设
    CONFIRM_TARGET = "confirm_target"       # 确认逆向目标请求


class Decision(BaseModel):
    """人工决策点"""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    stage: str
    decision_type: DecisionType
    prompt: str                             # 展示给用户的问题/说明
    options: list[str] | None = None        # SELECT_OPTION 时的选项列表
    artifact_path: Path | None = None       # EDIT_ARTIFACT 时展示的文件
    context_summary: str = ""              # 简短上下文摘要
    default: str | None = None             # 自动模式下使用的默认值
    # 决策后填充
    outcome: str | None = None
    rationale: str | None = None           # 用户可填写的决策理由

    model_config = {"arbitrary_types_allowed": True}


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"       # 等待人工决策
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class StageRecord(BaseModel):
    """单阶段执行记录"""
    stage_name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: dict[str, str] = {}         # 名称 → 文件路径字符串
    decisions: list[Decision] = []
    error: str | None = None


class PipelineState(BaseModel):
    """流水线运行状态（可持久化/恢复）"""
    session_id: str
    mode: str = "interactive"              # interactive / auto / manual
    current_stage_index: int = 0
    stages: list[StageRecord] = []
    # 全局产物索引
    artifacts: dict[str, str] = {}        # key → 文件路径字符串
    # 运行信息
    started_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    completed: bool = False
    error: str | None = None

    def get_stage(self, name: str) -> StageRecord | None:
        for s in self.stages:
            if s.stage_name == name:
                return s
        return None

    def set_artifact(self, key: str, path: Path) -> None:
        self.artifacts[key] = str(path)

    def get_artifact(self, key: str) -> Path | None:
        val = self.artifacts.get(key)
        return Path(val) if val else None


class StageResult(BaseModel):
    """阶段执行返回值"""
    stage_name: str
    success: bool
    artifacts: dict[str, Path] = {}
    decisions: list[Decision] = []
    summary: str = ""                      # 给用户看的简短总结
    error: str | None = None
    duration_seconds: float = 0.0
    # 传递给下一阶段的数据（非文件型）
    next_input: dict[str, Any] = {}

    model_config = {"arbitrary_types_allowed": True}
