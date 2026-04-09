"""
Crypto Tool - 加密分析工具

从 analysis.crypto 重写，封装加密检测功能
"""
from __future__ import annotations

import re
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
class CryptoOutput:
    """加密分析输出"""
    algorithms: list[str] = field(default_factory=list)
    key_locations: list[dict] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)


class CryptoTool(BaseTool):
    """加密分析工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "crypto"
    
    @property
    def description(self) -> str:
        return "加密分析：检测 JavaScript 中的加密使用 (AES, RSA, HMAC, SHA)"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.CRYPTO,
            input_schema=[
                ToolInput(
                    name="js_code",
                    type="string",
                    description="JavaScript 代码",
                    required=True,
                ),
            ],
            output_schema=[
                ToolOutput(name="algorithms", type="array", description="检测到的算法"),
                ToolOutput(name="key_locations", type="array", description="密钥位置"),
                ToolOutput(name="patterns", type="array", description="加密模式"),
            ],
            timeout_seconds=60,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行加密分析"""
        js_code = input_data.get("js_code")
        
        if not js_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code",
            )
        
        try:
            output = self._analyze(js_code)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "algorithms": output.algorithms,
                    "key_locations": output.key_locations,
                    "patterns": output.patterns,
                },
            )
            
        except Exception as exc:
            log.error("crypto_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _analyze(self, code: str) -> CryptoOutput:
        """分析加密使用"""
        output = CryptoOutput()
        
        # 检测算法
        algorithms = []
        patterns = [
            ("AES", r'CryptoJS\.AES|AES\.encrypt|AES\.decrypt'),
            ("DES", r'CryptoJS\.DES|DES\.encrypt|DES\.decrypt'),
            ("RSA", r'CryptoJS\.RSA|RSASSA-PKCS1-v1_5| RSA'),
            ("HMAC", r'CryptoJS\.HMAC|HMAC'),
            ("SHA1", r'CryptoJS\.SHA1|SHA1\('),
            ("SHA256", r'CryptoJS\.SHA256|SHA256\('),
            ("MD5", r'CryptoJS\.MD5|MD5\('),
        ]
        
        for name, pattern in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                algorithms.append(name)
                output.algorithms.append(name)
        
        # 检测密钥位置
        key_patterns = [
            (r'key\s*[:=]\s*["\']([^"\']{10,})["\']', "string_literal"),
            (r'password\s*[:=]\s*["\']([^"\']{10,})["\']', "string_literal"),
            (r'secret\s*[:=]\s*["\']([^"\']{10,})["\']', "string_literal"),
            (r'CryptoJS\.enc\.Utf8\.parse\(["\']([^"\']+)["\']\)', "crypto_parse"),
        ]
        
        for pattern, ptype in key_patterns:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                output.key_locations.append({
                    "type": ptype,
                    "value_preview": match.group(1)[:50],
                    "position": match.start(),
                })
        
        # 简化模式
        output.patterns = [{"algorithm": a, "confidence": "high"} for a in output.algorithms]
        
        return output


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(CryptoTool())
