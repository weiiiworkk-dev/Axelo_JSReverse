from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


OutputMode = Literal["standalone", "bridge", "both"]


class GeneratedCode(BaseModel):
    """代码生成产物"""
    session_id: str
    output_mode: OutputMode
    generated_at: datetime = Field(default_factory=datetime.now)

    # 独立脚本模式
    standalone_script_path: Path | None = None
    standalone_deps: list[str] = []       # pip 依赖列表

    # 桥接代理模式
    bridge_client_path: Path | None = None
    bridge_server_path: Path | None = None
    bridge_port: int = 8721

    # 验证结果
    verified: bool = False
    verification_notes: str = ""

    model_config = {"arbitrary_types_allowed": True}
