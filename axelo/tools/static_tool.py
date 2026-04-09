"""
Static Tool - 静态分析工具

从 s4_static 重写，封装静态分析功能
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
class StaticAnalysisOutput:
    """静态分析输出"""
    candidates: list[dict] = field(default_factory=list)
    api_endpoints: list[str] = field(default_factory=list)
    signature_candidates: list[dict] = field(default_factory=list)
    crypto_usage: list[dict] = field(default_factory=list)


class StaticTool(BaseTool):
    """静态分析工具"""
    
    def __init__(self):
        super().__init__()
    
    @property
    def name(self) -> str:
        return "static"
    
    @property
    def description(self) -> str:
        return "静态分析：从 JavaScript 代码中提取签名候选项"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.ANALYSIS,
            input_schema=[
                ToolInput(
                    name="js_code",
                    type="string",
                    description="JavaScript 代码",
                    required=True,
                ),
                ToolInput(
                    name="url",
                    type="string",
                    description="来源 URL",
                    required=False,
                ),
                ToolInput(
                    name="options",
                    type="object",
                    description="分析选项",
                    required=False,
                    default={},
                ),
            ],
            output_schema=[
                ToolOutput(name="candidates", type="array", description="签名候选项"),
                ToolOutput(name="api_endpoints", type="array", description="API 端点"),
                ToolOutput(name="signature_candidates", type="array", description="签名候选"),
                ToolOutput(name="crypto_usage", type="array", description="加密使用"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行静态分析"""
        js_code = input_data.get("js_code") or input_data.get("content")
        
        # 处理 bundles 列表
        if not js_code and "bundles" in input_data:
            bundles = input_data["bundles"]
            if isinstance(bundles, list):
                # 拼接前 5 个最相关的 bundle
                js_code = "\n\n".join([b.get("content", "") for b in bundles[:5]])
        
        if not js_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code",
            )
        
        try:
            output = StaticAnalysisOutput()
            
            # 1. 提取 API 端点
            output.api_endpoints = self._extract_endpoints(js_code)
            
            # 2. 提取签名候选
            output.signature_candidates = self._extract_signatures(js_code)
            
            # 3. 提取加密使用
            output.crypto_usage = self._extract_crypto_usage(js_code)
            
            # 4. 提取通用候选
            output.candidates = self._extract_candidates(js_code)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "candidates": output.candidates,
                    "api_endpoints": output.api_endpoints,
                    "signature_candidates": output.signature_candidates,
                    "crypto_usage": output.crypto_usage,
                },
            )
            
        except Exception as exc:
            log.error("static_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    def _extract_endpoints(self, code: str) -> list[str]:
        """提取 API 端点"""
        endpoints = []
        
        # 匹配 fetch/XHR 调用
        patterns = [
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
            r'XHR\s*\(\s*["\']([^"\']+)["\']',
            r'axios\.[get|post|put|delete]\s*\(\s*["\']([^"\']+)["\']',
            r'\$\.ajax\s*\(\s*{\s*url\s*:\s*["\']([^"\']+)["\']',
            r'await\s+fetch\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                if url and url.startswith("/"):
                    endpoints.append(url)
        
        return list(set(endpoints))[:50]
    
    def _extract_signatures(self, code: str) -> list[dict]:
        """提取签名候选"""
        candidates = []
        
        # 签名相关模式
        patterns = {
            "sign": r'(?:sign|Sign)\s*\([^)]*\)',
            "signature": r'(?:signature|Signature)\s*[:=]\s*[^,;]+',
            "token": r'(?:token|Token)\s*[:=]\s*[^,;]+',
            "hash": r'(?:hash|Hash)\s*\([^)]*\)',
            "hmac": r'(?:hmac|HMAC)\s*\([^)]*\)',
            "encrypt": r'(?:encrypt|Encrypt)\s*\([^)]*\)',
        }
        
        for name, pattern in patterns.items():
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                candidates.append({
                    "type": name,
                    "code": match.group(0)[:200],
                    "line": code[:match.start()].count("\n") + 1,
                })
        
        return candidates[:30]
    
    def _extract_crypto_usage(self, code: str) -> list[dict]:
        """提取加密使用"""
        crypto = []
        
        # Crypto API
        crypto_apis = {
            "AES": r'CryptoJS\.AES\.',
            "RSA": r'CryptoJS\.RSA\.',
            "HMAC": r'CryptoJS\.HMAC\.',
            "SHA256": r'CryptoJS\.SHA256\(',
            "MD5": r'CryptoJS\.MD5\(',
            "window.crypto": r'window\.crypto\.',
            "SubtleCrypto": r'crypto\.subtle\.',
        }
        
        for name, pattern in crypto_apis.items():
            if re.search(pattern, code):
                crypto.append({
                    "algorithm": name,
                    "detected": True,
                })
        
        return crypto
    
    def _extract_candidates(self, code: str) -> list[dict]:
        """提取通用候选"""
        candidates = []
        
        # 提取变量赋值
        var_pattern = r'(?:const|let|var)\s+(\w+)\s*=\s*([^;]{10,200});'
        for match in re.finditer(var_pattern, code):
            name = match.group(1)
            value = match.group(2).strip()
            
            # 过滤可能相关的变量
            if any(kw in name.lower() for kw in ["key", "token", "sig", "auth", "param", "req"]):
                candidates.append({
                    "type": "variable",
                    "name": name,
                    "value_preview": value[:100],
                })
        
        return candidates[:20]


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(StaticTool())
