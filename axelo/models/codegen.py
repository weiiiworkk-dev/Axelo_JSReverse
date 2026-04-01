from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


OutputMode = Literal["standalone", "bridge"]


class GeneratedCode(BaseModel):
    """代码生成产物"""
    session_id: str
    output_mode: OutputMode
    generated_at: datetime = Field(default_factory=datetime.now)

    # 爬虫脚本（独立模式：包含签名+请求；桥接模式：包含签名调用+请求）
    crawler_script_path: Path | None = None
    crawler_deps: list[str] = []       # pip 依赖列表

    # 桥接服务（仅 bridge 模式）
    bridge_server_path: Path | None = None
    bridge_port: int = 8721

    # 验证结果
    verified: bool = False
    verification_notes: str = ""

    model_config = {"arbitrary_types_allowed": True}
