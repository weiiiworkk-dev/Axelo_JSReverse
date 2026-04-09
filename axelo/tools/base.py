"""
MCP Tool Schema 定义

Axelo 工具系统的核心 schema 定义，基于 MCP (Model Context Protocol) 标准
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar, Generic

import structlog

log = structlog.get_logger()


# ============================================================
# Tool Schema - 输入/输出定义
# ============================================================

@dataclass
class ToolInput:
    """Tool 输入参数定义"""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] = None


@dataclass
class ToolOutput:
    """Tool 输出定义"""
    name: str
    type: str
    description: str


@dataclass
class ToolSchema:
    """完整的 Tool Schema 定义"""
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"  # browser, analysis, ai, codegen, verify
    
    input_schema: list[ToolInput] = field(default_factory=list)
    output_schema: list[ToolOutput] = field(default_factory=list)
    
    # Tool 元数据
    timeout_seconds: int = 300
    retry_enabled: bool = True
    max_retries: int = 3
    
    # 依赖关系 (动态推断)
    requires: list[str] = field(default_factory=list)  # 需要哪些其他 tools
    provides: list[str] = field(default_factory=list)  # 提供哪些数据


# ============================================================
# Tool 执行结果
# ============================================================

class ToolStatus(Enum):
    """Tool 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


@dataclass
class ToolResult:
    """Tool 执行结果"""
    tool_name: str
    status: ToolStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_seconds: float = 0.0
    retries: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def success(self) -> bool:
        return self.status == ToolStatus.SUCCESS


# ============================================================
# Tool 状态存储
# ============================================================

@dataclass
class ToolState:
    """Tool 执行状态存储"""
    results: dict[str, ToolResult] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    
    def save_result(self, result: ToolResult) -> None:
        """保存 tool 执行结果"""
        self.results[result.tool_name] = result
    
    def get_result(self, tool_name: str) -> ToolResult | None:
        """获取 tool 执行结果"""
        return self.results.get(tool_name)
    
    def get_output(self, tool_name: str) -> dict[str, Any]:
        """获取 tool 输出数据"""
        result = self.get_result(tool_name)
        return result.output if result else {}
    
    def set_context(self, key: str, value: Any) -> None:
        """设置上下文数据"""
        self.context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        return self.context.get(key, default)


# ============================================================
# Base Tool 抽象类
# ============================================================

class BaseTool(ABC):
    """所有 Axelo Tools 的基类"""
    
    def __init__(self):
        self._schema: ToolSchema | None = None
        self._state: ToolState | None = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool 名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool 描述"""
        pass
    
    @property
    def schema(self) -> ToolSchema:
        """获取 Tool Schema"""
        if self._schema is None:
            self._schema = self._create_schema()
        return self._schema
    
    @abstractmethod
    def _create_schema(self) -> ToolSchema:
        """创建 Tool Schema - 子类实现"""
        pass
    
    @abstractmethod
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """
        执行 Tool
        
        Args:
            input_data: 输入参数
            state: 工具状态存储
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    async def run(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """带错误处理和重试的执行封装"""
        import time
        t0 = time.monotonic()
        
        retries = 0
        max_retries = self.schema.max_retries if self.schema else 3
        
        while True:
            try:
                state.set_context("current_tool", self.name)
                result = await self.execute(input_data, state)
                result.duration_seconds = time.monotonic() - t0
                return result
            except Exception as exc:
                retries += 1
                if retries >= max_retries or not self.schema.retry_enabled:
                    log.error("tool_failed", tool=self.name, error=str(exc), retries=retries)
                    return ToolResult(
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        error=str(exc),
                        duration_seconds=time.monotonic() - t0,
                        retries=retries
                    )
                log.warning("tool_retrying", tool=self.name, error=str(exc), retry=retries)
                await self._on_retry(exc, retries)
    
    async def _on_retry(self, error: Exception, attempt: int) -> None:
        """重试前钩子"""
        import asyncio
        # 指数退避: 1s, 2s, 4s, ...
        wait_time = min(2 ** (attempt - 1), 30)
        await asyncio.sleep(wait_time)
    
    def validate_input(self, input_data: dict[str, Any]) -> tuple[bool, str]:
        """验证输入参数"""
        for inp in self.schema.input_schema:
            if inp.required and inp.name not in input_data:
                return False, f"Missing required input: {inp.name}"
        return True, ""


# ============================================================
# Tool 注册表
# ============================================================

class ToolRegistry:
    """Tool 注册表 - 管理所有可用工具"""
    
    _instance: "ToolRegistry | None" = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance
    
    def __init__(self):
        # 确保 _tools 存在
        if not hasattr(self, '_tools'):
            self._tools = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册 Tool"""
        self._tools[tool.name] = tool
        log.info("tool_registered", tool=tool.name)
    
    def get(self, name: str) -> BaseTool | None:
        """获取 Tool"""
        return self._tools.get(name)
    
    def list_tools(self) -> list[str]:
        """列出所有 Tool 名称"""
        return list(self._tools.keys())
    
    def get_schemas(self) -> list[ToolSchema]:
        """获取所有 Tool Schema"""
        return [tool.schema for tool in self._tools.values()]
    
    def get_by_category(self, category: str) -> list[BaseTool]:
        """按类别获取 Tools"""
        return [
            tool for tool in self._tools.values()
            if tool.schema.category == category
        ]


def get_registry() -> ToolRegistry:
    """获取 Tool 注册表单例"""
    return ToolRegistry()


# ============================================================
# Tool 装饰器
# ============================================================

def register_tool(cls: type[BaseTool]) -> type[BaseTool]:
    """Tool 注册装饰器"""
    get_registry().register(cls())
    return cls


# ============================================================
# 预定义 Categories
# ============================================================

class ToolCategory:
    """Tool 类别常量"""
    BROWSER = "browser"      # 浏览器操作
    FETCH = "fetch"           # 数据获取
    ANALYSIS = "analysis"    # 分析
    CRYPTO = "crypto"        # 加密分析
    DYNAMIC = "dynamic"      # 动态分析
    AI = "ai"                # AI 分析
    CODEGEN = "codegen"      # 代码生成
    VERIFY = "verify"        # 验证
    DETECTION = "detection"  # 反检测
    FLOW = "flow"            # 数据流
