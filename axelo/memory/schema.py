from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
import uuid


class SitePattern(SQLModel, table=True):
    """已知站点逆向模式记录"""
    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(index=True)                 # 站点域名
    url_pattern: str = ""                            # URL 正则特征
    algorithm_type: str = ""                         # hmac/rsa/aes/custom
    difficulty: str = "medium"                       # easy/medium/hard/extreme
    solution_template_id: Optional[int] = Field(default=None, foreign_key="solutiontemplate.id")
    verified: bool = False
    success_count: int = 0
    fail_count: int = 0
    last_seen: datetime = Field(default_factory=datetime.now)
    notes: str = ""
    # === Enhanced fields for learning ===
    signature_headers: str = ""                      # JSON: known signature headers
    antibot_error_codes: str = ""                    # JSON: known anti-bot error codes
    requires_bridge: bool = False                    # Whether site needs bridge mode
    session_refresh_needed: bool = False             # Whether session needs refresh


class JSBundleCache(SQLModel, table=True):
    """JS Bundle 分析结果缓存"""
    id: Optional[int] = Field(default=None, primary_key=True)
    content_hash: str = Field(index=True, unique=True)  # SHA256[:16]
    bundle_type: str = ""
    deobfuscation_tool: str = ""
    token_candidate_count: int = 0
    crypto_primitives: str = ""           # JSON list
    algorithm_type: str = ""
    analysis_json: str = ""               # 完整 StaticAnalysis JSON
    vector_id: Optional[int] = None       # FAISS 中的向量 ID
    created_at: datetime = Field(default_factory=datetime.now)


class SolutionTemplate(SQLModel, table=True):
    """逆向解法模板（可复用的算法实现）"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                             # 模板名称，如 "hmac-sha256-timestamp"
    algorithm_type: str                   # hmac/rsa/aes/fingerprint/custom
    description: str = ""
    python_code: str = ""                 # 模板 Python 代码（含占位符）
    bridge_code: str = ""                 # 模板 JS 桥接代码
    input_fields: str = ""               # JSON list of required inputs
    output_fields: str = ""              # JSON list of output header names
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ReverseSession(SQLModel, table=True):
    """完整逆向会话记录（用于经验积累）"""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    url: str
    domain: str = Field(index=True)
    goal: str = ""
    difficulty: str = "unknown"
    algorithm_type: str = "unknown"
    codegen_strategy: str = ""           # python_reconstruct / js_bridge
    ai_confidence: float = 0.0
    verified: bool = False
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    # 关键经验摘要（喂给向量库）
    experience_summary: str = ""
    static_features: str = ""           # JSON: crypto_imports, env_access 等
    hook_trace_summary: str = ""
    hypothesis_json: str = ""
    solution_template_id: Optional[int] = Field(default=None, foreign_key="solutiontemplate.id")
    created_at: datetime = Field(default_factory=datetime.now)
