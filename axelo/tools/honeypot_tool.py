"""
Honeypot Tool - 蜜罐检测工具

从 detection 重写，封装蜜罐检测功能
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
class HoneypotOutput:
    """蜜罐检测输出"""
    is_honeypot: bool = False
    risk_score: float = 0.0
    hidden_fields: list[dict] = field(default_factory=list)
    trap_links: list[dict] = field(default_factory=list)
    decoy_data: list[dict] = field(default_factory=list)


class HoneypotTool(BaseTool):
    """蜜罐检测工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "honeypot"
    
    @property
    def description(self) -> str:
        return "蜜罐检测：检测网页中的蜜罐陷阱"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.DETECTION,
            input_schema=[
                ToolInput(
                    name="html",
                    type="string",
                    description="HTML 内容",
                    required=True,
                ),
                ToolInput(
                    name="url",
                    type="string",
                    description="页面 URL",
                    required=False,
                ),
            ],
            output_schema=[
                ToolOutput(name="is_honeypot", type="boolean", description="是否蜜罐"),
                ToolOutput(name="risk_score", type="number", description="风险分数"),
                ToolOutput(name="hidden_fields", type="array", description="隐藏字段"),
                ToolOutput(name="trap_links", type="array", description="陷阱链接"),
                ToolOutput(name="decoy_data", type="array", description="诱饵数据"),
            ],
            timeout_seconds=30,
            retry_enabled=False,
            max_retries=1,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行蜜罐检测"""
        html = input_data.get("html")
        
        if not html:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: html",
            )
        
        try:
            output = self._detect(input_data)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "is_honeypot": output.is_honeypot,
                    "risk_score": output.risk_score,
                    "hidden_fields": output.hidden_fields,
                    "trap_links": output.trap_links,
                    "decoy_data": output.decoy_data,
                },
            )
            
        except Exception as exc:
            log.error("honeypot_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _detect(self, input_data: dict) -> HoneypotOutput:
        """执行检测"""
        import re
        
        output = HoneypotOutput()
        html = input_data.get("html", "")
        
        # 1. 检测隐藏字段
        hidden_patterns = [
            r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']',
            r'<input[^>]*name=["\']([^"\']*honeypot[^"\']*)["\'][^>]*>',
            r'<input[^>]*name=["\']([^"\']*trap[^"\']*)["\'][^>]*>',
        ]
        
        for pattern in hidden_patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                output.hidden_fields.append({
                    "name": match.group(1),
                    "matched": match.group(0)[:100],
                })
        
        # 2. 检测陷阱链接
        trap_patterns = [
            r'<a[^>]*href=["\'][^"\']*#?bot[^"\']*["\'][^>]*>',
            r'<a[^>]*href=["\'][^"\']*spider[^"\']*["\'][^>]*>',
            r'<a[^>]*display\s*:\s*none[^>]*>',
        ]
        
        for pattern in trap_patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                output.trap_links.append({
                    "matched": match.group(0)[:100],
                })
        
        # 3. 计算风险分数
        risk = 0
        if output.hidden_fields:
            risk += len(output.hidden_fields) * 0.3
        if output.trap_links:
            risk += len(output.trap_links) * 0.3
        
        output.risk_score = min(risk, 1.0)
        output.is_honeypot = output.risk_score > 0.5
        
        return output


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(HoneypotTool())
