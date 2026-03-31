from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class FunctionSignature(BaseModel):
    """函数节点（从 AST 提取）"""
    func_id: str                         # bundle_id + ":" + name_or_offset
    name: str | None = None
    source_file: str = ""
    line: int = 0
    col: int = 0
    params: list[str] = []
    is_async: bool = False
    calls: list[str] = []               # 调用的函数ID列表
    called_by: list[str] = []
    cyclomatic_complexity: int = 1
    raw_source: str = ""                # 函数原始源码片段（用于喂给AI）


TokenType = Literal[
    "hmac", "sha256", "md5", "aes",
    "timestamp", "nonce", "uuid",
    "fingerprint", "base64", "custom",
    "unknown",
]


class TokenCandidate(BaseModel):
    """疑似签名/token生成函数"""
    func_id: str
    token_type: TokenType = "unknown"
    confidence: float = 0.0             # 0-1
    evidence: list[str] = []            # 可读的证据描述
    request_field: str | None = None    # 对应的请求头/body字段
    source_snippet: str = ""            # 关键代码片段


class StaticAnalysis(BaseModel):
    """单个 Bundle 的静态分析结果"""
    bundle_id: str
    entry_points: list[str] = []
    function_map: dict[str, FunctionSignature] = {}   # func_id → FunctionSignature
    token_candidates: list[TokenCandidate] = []
    crypto_imports: list[str] = []      # 检测到的加密库/API使用
    env_access: list[str] = []          # window.*/navigator.*/document.* 访问
    string_constants: list[str] = []    # 解码后的关键字符串常量
    call_graph_path: str | None = None  # 调用图可视化（dot格式路径）


class HookIntercept(BaseModel):
    """单次 Hook 拦截记录"""
    api_name: str                        # 如 "crypto.subtle.sign"
    args_repr: str                       # 参数的可序列化表示（hex/base64/json）
    return_repr: str
    stack_trace: list[str] = []
    timestamp: float = 0.0
    sequence: int = 0                   # 全局调用序号


class DynamicAnalysis(BaseModel):
    """动态执行分析结果（Hook + 时序关联）"""
    bundle_id: str
    hook_intercepts: list[HookIntercept] = []
    # 从Hook时序中推断出的生成器函数
    confirmed_generators: list[str] = []   # func_id 列表
    # Hook调用 → 目标请求字段的映射
    field_mapping: dict[str, str] = {}    # hook_api_name → request_field
    crypto_primitives: list[str] = []     # 实际使用的加密原语名称


class AIHypothesis(BaseModel):
    """AI 分析输出的算法假设"""
    algorithm_description: str          # 自然语言描述
    generator_func_ids: list[str] = []  # 核心生成函数
    steps: list[str] = []               # 算法步骤列表（有序）
    inputs: list[str] = []              # 算法输入（url/body/timestamp/key...）
    outputs: dict[str, str] = {}        # 输出字段 → 描述
    codegen_strategy: Literal["python_reconstruct", "js_bridge"] = "js_bridge"
    python_feasibility: float = 0.0     # 0-1，Python还原可行性
    confidence: float = 0.0
    notes: str = ""                     # 额外备注（如：依赖浏览器环境，建议桥接）


class AnalysisResult(BaseModel):
    """全流水线分析汇总"""
    session_id: str
    static: dict[str, StaticAnalysis] = {}    # bundle_id → StaticAnalysis
    dynamic: DynamicAnalysis | None = None
    ai_hypothesis: AIHypothesis | None = None
    overall_confidence: float = 0.0
    ready_for_codegen: bool = False
