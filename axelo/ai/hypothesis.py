from __future__ import annotations
from pydantic import BaseModel, Field


class AIHypothesisOutput(BaseModel):
    """
    AI 分析的结构化输出，通过 tool_use 直接反序列化。
    字段名和描述会成为 tool schema，影响 AI 输出质量。
    """
    algorithm_description: str = Field(
        description="用自然语言详细描述签名/Token 的生成算法，包括数据来源、处理步骤和最终格式"
    )
    generator_func_ids: list[str] = Field(
        default_factory=list,
        description="负责生成签名/Token 的核心函数标识符（来自静态分析的 func_id）"
    )
    steps: list[str] = Field(
        default_factory=list,
        description="算法的有序步骤列表，每步一句话描述（如：1. 获取当前时间戳毫秒值）"
    )
    inputs: list[str] = Field(
        default_factory=list,
        description="算法所有输入参数，如：请求URL、请求体MD5、时间戳、固定密钥等"
    )
    outputs: dict[str, str] = Field(
        default_factory=dict,
        description="输出字段名 → 描述，如：{'X-Sign': 'HMAC-SHA256 签名的 hex 编码'}"
    )
    codegen_strategy: str = Field(
        default="js_bridge",
        description="代码生成策略：'python_reconstruct'（可用 Python 重写）或 'js_bridge'（需保留 JS 执行环境）"
    )
    python_feasibility: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Python 重写可行性评分 0-1，1 表示完全可行（仅使用标准加密算法），0 表示严重依赖浏览器环境"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="整体分析置信度 0-1，基于证据充分程度"
    )
    notes: str = Field(
        default="",
        description="补充说明：如依赖的浏览器特性、混淆难点、建议的验证方式等"
    )


class CodeGenOutput(BaseModel):
    """代码生成的结构化输出"""
    standalone_code: str = Field(
        default="",
        description="独立 Python 脚本完整代码（含 import、类定义、测试用例）"
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="需要安装的 pip 依赖列表，如：['pycryptodome>=3.20.0']"
    )
    bridge_server_code: str = Field(
        default="",
        description="Node.js bridge server 完整代码"
    )
    bridge_client_code: str = Field(
        default="",
        description="Python bridge client 完整代码"
    )
    notes: str = Field(
        default="",
        description="实现说明、已知限制、使用方法"
    )
