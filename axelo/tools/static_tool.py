"""
Static Tool - 静态分析工具

从 s4_static 重写，封装静态分析功能
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
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

from axelo.config import settings

log = structlog.get_logger()
DEBUG_LOG_PATH = settings.workspace / "debug.log"
DEBUG_SESSION_ID = "default"


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        # #region agent log
        _debug_log(
            run_id="run",
            hypothesis_id="H2",
            location="axelo/tools/static_tool.py:execute:entry",
            message="static received input",
            data={
                "keys": sorted(list(input_data.keys())),
                "has_js_code": bool(input_data.get("js_code")),
                "has_content": bool(input_data.get("content")),
                "has_html_content": bool(input_data.get("html_content")),
                "has_bundles": bool(input_data.get("bundles")),
                "has_js_bundles": bool(input_data.get("js_bundles")),
                "content_len": len(input_data.get("content") or ""),
                "html_content_len": len(input_data.get("html_content") or ""),
            },
        )
        # #endregion
        js_code = input_data.get("js_code") or input_data.get("content")
        
        # 处理 bundles 列表
        if not js_code and "bundles" in input_data:
            bundles = input_data["bundles"]
            if isinstance(bundles, list):
                # 拼接前 5 个最相关的 bundle
                js_code = "\n\n".join([b.get("content", "") for b in bundles[:5]])
        
        if not js_code:
            # #region agent log
            _debug_log(
                run_id="run",
                hypothesis_id="H2",
                location="axelo/tools/static_tool.py:execute:missing_js",
                message="js_code missing before static failure",
                data={
                    "keys": sorted(list(input_data.keys())),
                    "content_len": len(input_data.get("content") or ""),
                    "html_content_len": len(input_data.get("html_content") or ""),
                },
            )
            # #endregion
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
                    # 新增: 原始端点列表供下游使用
                    "endpoints": output.api_endpoints,
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
        """提取 API 端点 - 增强版"""
        endpoints = []
        
        # 匹配 fetch/XHR 调用 - 基础模式
        basic_patterns = [
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
            r'XHR\s*\(\s*["\']([^"\']+)["\']',
            r'axios\.[get|post|put|delete]\s*\(\s*["\']([^"\']+)["\']',
            r'\$\.ajax\s*\(\s*{\s*url\s*:\s*["\']([^"\']+)["\']',
            r'await\s+fetch\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        # 扩展模式 - 检测更多 API 调用
        extended_patterns = [
            # XMLHttpRequest
            r'new\s+XMLHttpRequest\(\)[\s\S]{0,200}\.open\s*\(\s*["\'][A-Z]+["\']\s*,\s*["\']([^"\']+)["\']',
            # URL 构造
            r'(?:baseURL|apiBase|apiUrl)\s*[:=]\s*["\']([^"\']+)["\']',
            # REST API 常见路径
            r'["\']\/api\/[v\d]+\/[^"\']+["\']',
            # 搜索端点常见模式
            r'["\']\/search["\'].*?["\']\/([^"\']+)["\']',
            # encodeURIComponent 包裹的端点
            r'encodeURIComponent\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        # 基础模式匹配
        for pattern in basic_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                url = match.group(1)
                if url and url.startswith("/"):
                    endpoints.append(url)
        
        # 扩展模式匹配
        for pattern in extended_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                url = match.group(1) if match.lastindex else match.group(0)
                if url and ("/api/" in url or url.startswith("/")):
                    endpoints.append(url)
        
        # 额外模式：搜索页面常用的 API 端点模式
        search_patterns = [
            # 通用搜索端点模式
            r's.*\?.*k=',
            r'/gp/search/',
            r'/ajax/search',
            # 标准搜索路径
            r'/search\?',
            r'/products\?',
            r'/items\?',
            r'/search',
        ]
        
        # 从 URL 参数中提取可能的端点
        url_param_pattern = r'(?:url|endpoint|path|api)\s*[:=]\s*["\']([^"\']+)["\']'
        matches = re.finditer(url_param_pattern, code, re.IGNORECASE)
        for match in matches:
            url = match.group(1)
            if url and (url.startswith("/") or "api" in url.lower()):
                endpoints.append(url)
        
        # 去重并返回
        unique_endpoints = list(set(endpoints))[:50]
        
        # 如果没有找到端点，添加一些常见的搜索端点作为候选
        if not unique_endpoints:
            common_endpoints = [
                "/search",
                "/api/search",
                "/products/search",
                "/ajax/search",
            ]
            return common_endpoints[:5]
        
        return unique_endpoints
    
    def _extract_signatures(self, code: str) -> list[dict]:
        """提取签名候选 - 增强版"""
        candidates = []
        
        # 签名相关模式 - 更全面
        patterns = {
            "sign": r'(?:function\s+)?(?:sign|Sign)\s*(?:\([^)]*\)|\w+)\s*[{=>]?\s*[^}]*',
            "signature": r'(?:function\s+)?(?:signature|Signature)\s*(?:\([^)]*\)|\w+)\s*[{=>]?\s*[^}]*',
            "hash": r'(?:function\s+)?(?:hash|Hash)\s*(?:\([^)]*\)|\w+)\s*[{=>]?\s*[^}]*',
            "hmac": r'(?:function\s+)?(?:hmac|HMAC)\s*(?:\([^)]*\)|\w+)\s*[{=>]?\s*[^}]*',
            "encrypt": r'(?:function\s+)?(?:encrypt|Encrypt)\s*(?:\([^)]*\)|\w+)\s*[{=>]?\s*[^}]*',
            "md5": r'(?:MD5|md5)\s*\([^)]*\)',
            "sha": r'(?:SHA(?:1|256|512)?|sha(?:1|256|512)?)\s*\([^)]*\)',
            "base64": r'(?:Base64|base64)\s*\([^)]*\)',
        }
        
        for name, pattern in patterns.items():
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                # 计算行号
                line_num = code[:match.start()].count("\n") + 1
                # 提取函数体预览
                code_snippet = match.group(0)[:200]
                
                candidates.append({
                    "type": name,
                    "code": code_snippet,
                    "line": line_num,
                    "preview": code_snippet[:100],
                })
        
        # 额外的签名变量检测
        signature_vars = [
            r'(?:signature|sign|token|hash)\s*[:=]\s*(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*[a-zA-Z_][a-zA-Z0-9_]*\s*\(',
            r'getSignature\s*\(',
            r'generateSignature\s*\(',
            r'createSignature\s*\(',
        ]
        
        for pattern in signature_vars:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                line_num = code[:match.start()].count("\n") + 1
                candidates.append({
                    "type": "signature_call",
                    "code": match.group(0)[:200],
                    "line": line_num,
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
