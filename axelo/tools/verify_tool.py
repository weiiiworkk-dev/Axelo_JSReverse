"""
Verify Tool - 验证工具

从 s8_verify 重写，封装验证功能
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
class VerifyOutput:
    """验证输出"""
    success: bool = False
    score: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class VerifyTool(BaseTool):
    """验证工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "verify"
    
    @property
    def description(self) -> str:
        return "验证：验证生成的爬虫代码是否正确工作"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.VERIFY,
            input_schema=[
                ToolInput(
                    name="code",
                    type="string",
                    description="要验证的代码",
                    required=True,
                ),
                ToolInput(
                    name="target_url",
                    type="string",
                    description="目标 URL",
                    required=True,
                ),
                ToolInput(
                    name="test_params",
                    type="object",
                    description="测试参数",
                    required=False,
                    default={},
                ),
            ],
            output_schema=[
                ToolOutput(name="success", type="boolean", description="是否成功"),
                ToolOutput(name="score", type="number", description="验证分数"),
                ToolOutput(name="errors", type="array", description="错误列表"),
                ToolOutput(name="warnings", type="array", description="警告列表"),
                ToolOutput(name="details", type="object", description="详细信息"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行验证"""
        code = input_data.get("code") or input_data.get("python_code") or input_data.get("js_code")
        target_url = input_data.get("target_url") or input_data.get("page_url") or input_data.get("url")
        
        if not code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: code",
            )
        
        if not target_url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: target_url",
            )
        
        try:
            output = self._verify(input_data)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS if output.success else ToolStatus.FAILED,
                output={
                    "success": output.success,
                    "score": output.score,
                    "errors": output.errors,
                    "warnings": output.warnings,
                    "details": output.details,
                },
            )
            
        except Exception as exc:
            log.error("verify_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _verify(self, input_data: dict) -> VerifyOutput:
        """执行验证"""
        output = VerifyOutput()
        
        code = input_data.get("code", "")
        target_url = input_data.get("target_url", "")
        
        # 1. 语法检查
        errors, warnings = self._syntax_check(code)
        output.errors.extend(errors)
        output.warnings.extend(warnings)
        
        # 2. 依赖检查
        missing_deps = self._check_dependencies(code)
        if missing_deps:
            output.warnings.append(f"可能缺少依赖: {', '.join(missing_deps)}")
        
        # 3. URL 一致性检查
        if target_url not in code and target_url.replace("https://", "") not in code:
            output.warnings.append("代码中的 URL 与目标不匹配")
        
        # 4. 计算分数
        base_score = 100
        output.score = base_score - (len(output.errors) * 20) - (len(output.warnings) * 5)
        output.score = max(0, output.score) / 100.0
        
        # 5. 成功判断
        output.success = len(output.errors) == 0 and output.score >= 0.7
        
        # 详情
        output.details = {
            "syntax_errors": len(output.errors),
            "warnings_count": len(output.warnings),
            "code_length": len(code),
        }
        
        return output
    
    def _syntax_check(self, code: str) -> tuple[list[str], list[str]]:
        """语法检查"""
        errors = []
        warnings = []
        
        # Python 检查
        if "import asyncio" in code or "async def" in code:
            try:
                compile(code, "<string>", "exec")
            except SyntaxError as e:
                errors.append(f"语法错误: {e.msg} at line {e.lineno}")
        
        # 常见问题检查
        if "TODO" in code:
            warnings.append("代码包含 TODO 标记，可能未完成")
        
        if "YOUR_SECRET_KEY" in code or "secret_key" in code:
            warnings.append("代码包含占位符密钥，需要替换")
        
        return errors, warnings
    
    def _check_dependencies(self, code: str) -> list[str]:
        """检查依赖"""
        needed = []
        
        if "httpx" in code and "import httpx" not in code:
            needed.append("httpx")
        if "playwright" in code and "from playwright" not in code:
            needed.append("playwright")
        if "crypto" in code.lower() and "pycryptodome" not in code:
            needed.append("pycryptodome")
        
        return needed


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(VerifyTool())
