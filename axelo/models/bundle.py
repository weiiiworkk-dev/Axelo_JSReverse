from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel


BundleType = Literal["webpack", "vite", "rollup", "esbuild", "plain", "unknown"]
DeobfuscatorName = Literal["webcrack", "synchrony", "babel-manual", "none"]


class JSBundle(BaseModel):
    """下载并处理中的 JS Bundle"""
    bundle_id: str
    source_url: str
    raw_path: Path
    deobfuscated_path: Path | None = None
    ast_path: Path | None = None          # 序列化后的 Babel AST JSON 路径
    size_bytes: int = 0
    content_hash: str = ""               # SHA256，用于跨session缓存
    bundle_type: BundleType = "unknown"
    modules: list[str] = []             # webpack模块ID列表

    model_config = {"arbitrary_types_allowed": True}


class DeobfuscationResult(BaseModel):
    """去混淆结果"""
    bundle_id: str
    tool_used: DeobfuscatorName
    success: bool
    output_path: Path | None = None
    readability_score: float = 0.0      # 0-1，越高越可读
    original_score: float = 0.0
    error: str | None = None
    warnings: list[str] = []
    duration_seconds: float = 0.0

    model_config = {"arbitrary_types_allowed": True}
