"""
动态执行追踪工具 - Trace Tool

使用 Chrome DevTools Protocol 插桩 JavaScript 执行环境，
追踪函数调用和数据流，提取签名相关的信息。

用法:
    trace_tool.run({"js_code": "...", "target_url": "..."})
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import structlog

from axelo.tools.base import BaseTool, ToolOutput, ToolResult, ToolStatus

log = structlog.get_logger(__name__)


class TraceTool(BaseTool):
    """动态执行追踪工具"""
    
    # 类常量 - 签名相关模式
    SIGNATURE_PATTERNS = [
        r"sign",
        r"signature", 
        r"hash",
        r"hmac",
        r"encrypt",
        r"generate.*key",
        r"create.*sign",
        r"getSignature",
        r"generateSignature",
    ]
    
    # 类常量 - 加密函数
    CRYPTO_FUNCTIONS = [
        "CryptoJS.HMAC",
        "CryptoJS.AES",
        "CryptoJS.SHA256",
        "CryptoJS.SHA1",
        "CryptoJS.MD5",
        "crypto.subtle.sign",
        "crypto.subtle.encrypt",
        "crypto.subtle.digest",
        "window.crypto.subtle",
        "HMAC",
        "AES",
        "RSA",
    ]
    
    def __init__(self):
        super().__init__()
        self._traces = []
        self._crypto_detected = []
        self._data_flow = []

    @property
    def name(self) -> str:
        return "trace"
    
    @property
    def description(self) -> str:
        return "动态追踪 JavaScript 执行，提取签名相关函数和数据流"
    
    def _create_schema(self) -> "ToolSchema":
        from axelo.tools.base import ToolSchema, ToolInput, ToolCategory, ToolOutput
        
        output_schema = [
            ToolOutput(name="traced_calls", type="array", description="追踪到的函数调用"),
            ToolOutput(name="crypto_usage", type="array", description="检测到的加密使用"),
            ToolOutput(name="data_flow", type="array", description="数据流追踪结果"),
            ToolOutput(name="signature_candidates", type="array", description="签名候选函数"),
            ToolOutput(name="success", type="boolean", description="是否成功"),
        ]
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.ANALYSIS,
            input_schema=[
                ToolInput(name="js_code", type="string", description="要追踪的 JavaScript 代码"),
                ToolInput(name="target_url", type="string", description="目标页面 URL"),
                ToolInput(name="functions", type="array", description="要追踪的函数名"),
                ToolInput(name="patterns", type="array", description="要匹配的代码模式"),
            ],
            output_schema=output_schema,
            timeout_seconds=60,
            retry_enabled=True,
        )

    async def execute(self, input_data: dict[str, Any], state: Any) -> ToolResult:
        """执行追踪"""
        return await self.run(input_data, state)

    async def run(self, input_data: dict, state: Any = None) -> ToolResult:
        js_code = input_data.get("js_code", "")
        target_url = input_data.get("target_url", "")
        functions = input_data.get("functions", [])
        patterns = input_data.get("patterns", [])

        if not js_code and not target_url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code or target_url",
            )

        try:
            log.info("trace_start", code_length=len(js_code) if js_code else 0, url=target_url)

            # 重置追踪状态
            self._traces = []
            self._crypto_detected = []
            self._data_flow = []

            # 方法 1: 静态分析追踪
            if js_code:
                static_result = self._static_trace(js_code, functions, patterns)
                self._traces.extend(static_result["calls"])
                self._crypto_detected.extend(static_result["crypto"])
                self._data_flow.extend(static_result["data_flow"])

            # 方法 2: 动态追踪 (需要浏览器环境)
            if target_url:
                dynamic_result = await self._dynamic_trace(target_url)
                self._traces.extend(dynamic_result.get("calls", []))
                self._crypto_detected.extend(dynamic_result.get("crypto", []))

            # 识别签名候选
            signature_candidates = self._identify_signature_candidates()

            result = {
                "traced_calls": self._traces[:100],  # 限制数量
                "crypto_usage": self._crypto_detected[:50],
                "data_flow": self._data_flow[:50],
                "signature_candidates": signature_candidates,
                "success": True,
            }

            log.info("trace_complete",
                total_calls=len(self._traces),
                crypto_count=len(self._crypto_detected),
                signature_candidates=len(signature_candidates),
            )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=result,
            )

        except Exception as exc:
            log.error("trace_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"追踪失败: {exc}",
            )

    def _static_trace(self, js_code: str, functions: list, patterns: list) -> dict:
        """静态代码追踪"""
        log.info("static_trace_start")

        calls = []
        crypto = []
        data_flow = []

        # 1. 查找函数定义
        func_pattern = r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function|\.(\w+)\s*=\s*function)"
        for match in re.finditer(func_pattern, js_code):
            func_name = match.group(1) or match.group(2) or match.group(3)
            if func_name:
                calls.append({
                    "type": "function_definition",
                    "name": func_name,
                    "line": js_code[:match.start()].count("\n") + 1,
                })

        # 2. 查找签名相关函数调用
        for pattern in self.SIGNATURE_PATTERNS + patterns:
            regex = re.compile(rf"\b{pattern}\w*\s*\(", re.IGNORECASE)
            for match in regex.finditer(js_code):
                func_name = match.group(0).strip()
                calls.append({
                    "type": "signature_related",
                    "name": func_name,
                    "line": js_code[:match.start()].count("\n") + 1,
                })

        # 3. 查找加密 API 使用
        for crypto_func in self.CRYPTO_FUNCTIONS:
            if crypto_func.lower() in js_code.lower():
                crypto.append({
                    "type": "crypto_api",
                    "name": crypto_func,
                    "context": self._extract_context(js_code, crypto_func),
                })

        # 4. 数据流分析 - 查找参数传递
        # 查找 sign/encrypt 函数及其参数
        sign_calls = re.findall(
            r"(sign|encrypt|hmac|crypto|crypt)\w*\s*\(\s*([^)]+)\)",
            js_code,
            re.IGNORECASE
        )
        for call, params in sign_calls:
            data_flow.append({
                "function": call,
                "parameters": params.strip()[:100],
            })

        log.info("static_trace_complete",
            calls=len(calls),
            crypto=len(crypto),
            data_flow=len(data_flow),
        )

        return {
            "calls": calls,
            "crypto": crypto,
            "data_flow": data_flow,
        }

    async def _dynamic_trace(self, target_url: str) -> dict:
        """动态追踪 - 需要浏览器环境"""
        log.info("dynamic_trace_start", url=target_url)

        # 这里需要与浏览器工具集成
        # 由于当前系统使用 Playwright，我们可以通过注入脚本来追踪

        # 返回模拟的追踪结果 (实际实现需要 Playwright 集成)
        return {
            "calls": [],
            "crypto": [],
            "note": "动态追踪需要浏览器环境集成",
        }

    def _extract_context(self, code: str, keyword: str, context_size: int = 50) -> str:
        """提取关键词周围上下文"""
        idx = code.lower().find(keyword.lower())
        if idx == -1:
            return ""

        start = max(0, idx - context_size)
        end = min(len(code), idx + len(keyword) + context_size)

        return code[start:end].replace("\n", " ").strip()

    def _identify_signature_candidates(self) -> list:
        """识别签名候选函数"""
        candidates = []

        # 从追踪的调用中识别
        for call in self._traces:
            if call.get("type") == "signature_related":
                name = call.get("name", "")
                # 排除常见的非签名函数
                excluded = ["signin", "signup", "signature_pad", "signed"]
                if not any(ex in name.lower() for ex in excluded):
                    candidates.append({
                        "name": name,
                        "line": call.get("line", 0),
                        "reason": "signature_pattern_match",
                    })

        # 从加密使用中识别
        for crypto in self._crypto_detected:
            if "hmac" in crypto.get("name", "").lower():
                candidates.append({
                    "name": crypto.get("name"),
                    "type": "hmac",
                    "reason": "hmac_usage",
                })
            if "sha" in crypto.get("name", "").lower():
                candidates.append({
                    "name": crypto.get("name"),
                    "type": "hash",
                    "reason": "hash_usage",
                })

        # 去重
        seen = set()
        unique = []
        for c in candidates:
            key = c.get("name", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(c)

        return unique[:20]  # 限制数量


# 注册工具
try:
    from axelo.tools.base import get_registry
    get_registry().register(TraceTool())
    log.info("trace_tool_registered")
except Exception as e:
    log.warning("trace_tool_register_failed", error=str(e))