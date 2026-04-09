"""
Flow Tool - 数据流分析工具

从 data_flow_tracker 重写，封装数据流分析功能
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from axelo.tools.base import (
    BaseTool,
    ToolInput,
    ToolOutput,
    ToolSchema,
    ToolState,
    ToolResult,
    ToolStatus,
    ToolCategory,
)

log = structlog.get_logger()


@dataclass
class FlowNode:
    """数据流节点"""
    id: str
    type: str  # input, transform, output
    name: str
    code: str = ""


@dataclass
class FlowEdge:
    """数据流边"""
    from_node: str
    to_node: str
    label: str = ""


@dataclass
class FlowOutput:
    """数据流分析输出"""
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)


class FlowTool(BaseTool):
    """数据流分析工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "flow"
    
    @property
    def description(self) -> str:
        return "数据流分析：追踪数据在代码中的流动路径"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.FLOW,
            input_schema=[
                ToolInput(
                    name="js_code",
                    type="string",
                    description="JavaScript 代码",
                    required=True,
                ),
                ToolInput(
                    name="target",
                    type="string",
                    description="目标变量/函数名",
                    required=False,
                ),
            ],
            output_schema=[
                ToolOutput(name="nodes", type="array", description="数据流节点"),
                ToolOutput(name="edges", type="array", description="数据流边"),
                ToolOutput(name="entry_points", type="array", description="入口点"),
                ToolOutput(name="sinks", type="array", description="出口点"),
            ],
            timeout_seconds=60,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行数据流分析"""
        js_code = input_data.get("js_code")
        
        if not js_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code",
            )
        
        try:
            output = self._analyze(input_data)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "nodes": [
                        {"id": n.id, "type": n.type, "name": n.name, "code": n.code}
                        for n in output.nodes
                    ],
                    "edges": [
                        {"from": e.from_node, "to": e.to_node, "label": e.label}
                        for e in output.edges
                    ],
                    "entry_points": output.entry_points,
                    "sinks": output.sinks,
                },
            )
            
        except Exception as exc:
            log.error("flow_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _analyze(self, input_data: dict) -> FlowOutput:
        """执行数据流分析"""
        import re
        
        output = FlowOutput()
        code = input_data.get("js_code", "")
        target = input_data.get("target", "")
        
        # 1. 提取函数定义作为节点
        func_pattern = r'function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?function'
        
        for match in re.finditer(func_pattern, code):
            func_name = match.group(1) or match.group(2)
            output.nodes.append(FlowNode(
                id=f"func_{func_name}",
                type="transform",
                name=func_name,
            ))
        
        # 2. 提取变量赋值
        var_pattern = r'(?:let|const|var)\s+(\w+)\s*='
        
        for match in re.finditer(var_pattern, code):
            var_name = match.group(1)
            output.nodes.append(FlowNode(
                id=f"var_{var_name}",
                type="output",
                name=var_name,
            ))
        
        # 3. 提取 fetch/XHR 调用
        fetch_pattern = r'fetch\s*\(\s*["\']([^"\']+)["\']'
        
        for match in re.finditer(fetch_pattern, code):
            url = match.group(1)
            output.nodes.append(FlowNode(
                id=f"sink_{len(output.sinks)}",
                type="output",
                name="fetch",
                code=url,
            ))
            output.sinks.append(url)
        
        # 4. 入口点
        output.entry_points = [
            n.name for n in output.nodes if n.type == "transform"
        ][:10]
        
        return output


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(FlowTool())
