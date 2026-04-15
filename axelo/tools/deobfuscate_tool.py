"""
JS 反混淆工具 - Deobfuscate Tool

集成多个 JS 反混淆工具:
- webcrack: 反混淆 obfuscator.io, unpack webpack/bundler
- advanced_deobfuscator: 高级 Python AST 反混淆
- 内置 AST 基础反混淆

用法:
    deobfuscate_tool.run({"js_code": "...obfuscated js..."})
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

from axelo.tools.base import BaseTool, ToolOutput, ToolResult, ToolStatus

log = structlog.get_logger(__name__)

# 导入高级反混淆器
try:
    from axelo.tools.advanced_deobfuscator import advanced_deobfuscate
    HAS_ADVANCED = True
except ImportError:
    HAS_ADVANCED = False
    log.warning("advanced_deobfuscator not available")


class DeobfuscateTool(BaseTool):
    """JavaScript 反混淆工具"""

    def __init__(self):
        super().__init__()
        self._webcrack_path: Path | None = None
        self._ensure_tools()

    @property
    def name(self) -> str:
        return "deobfuscate"
    
    @property
    def description(self) -> str:
        return "反混淆 JavaScript 代码，支持 obfuscator.io、webpack 等"
    
    def _create_schema(self) -> "ToolSchema":
        from axelo.tools.base import ToolSchema, ToolInput, ToolCategory, ToolOutput
        
        output_schema = [
            ToolOutput(name="deobfuscated_code", type="string", description="反混淆后的代码"),
            ToolOutput(name="detected_type", type="string", description="检测到的混淆器类型"),
            ToolOutput(name="method_used", type="string", description="使用的反混淆方法"),
            ToolOutput(name="success", type="boolean", description="是否成功"),
        ]
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.ANALYSIS,
            input_schema=[
                ToolInput(name="js_code", type="string", description="要反混淆的 JavaScript 代码"),
                ToolInput(name="file_path", type="string", description="JS 文件路径"),
                ToolInput(name="obfuscator_type", type="string", description="已知混淆器类型"),
            ],
            output_schema=output_schema,
            timeout_seconds=60,
            retry_enabled=True,
        )

    async def execute(self, input_data: dict[str, Any], state: Any) -> ToolResult:
        """执行反混淆"""
        return await self.run(input_data, state)

    def _ensure_tools(self):
        """确保反混淆工具已安装"""
        # 检查 webcrack 是否可用
        try:
            result = subprocess.run(
                ["webcrack", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                self._webcrack_path = Path("webcrack")
                log.info("deobfuscate_tool_ready", tool="webcrack", method="cli")
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 检查本地安装
        node_modules = Path("node_modules/.bin/webcrack")
        if node_modules.exists():
            self._webcrack_path = node_modules
            log.info("deobfuscate_tool_ready", tool="webcrack", method="local")
            return

        # 使用内置方法
        log.info("deobfuscate_tool_ready", tool="builtin", method="ast")
        self._webcrack_path = None

    async def run(self, input_data: dict, state: Any = None) -> ToolResult:
        js_code = input_data.get("js_code", "")
        file_path = input_data.get("file_path", "")
        obfuscator_type = input_data.get("obfuscator_type", "")

        # 如果没有代码但有文件路径，从文件读取
        if not js_code and file_path:
            try:
                js_code = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"无法读取文件: {e}",
                )

        if not js_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code or file_path",
            )

        try:
            log.info("deobfuscate_start", code_length=len(js_code))

            # 方法 1: 如果知道混淆器类型，使用针对性的处理
            if obfuscator_type:
                result = await self._deobfuscate_by_type(js_code, obfuscator_type)
                if result["success"]:
                    return self._success_result(result)

            # 方法 2: 尝试 webcrack (如果可用)
            if self._webcrack_path:
                result = await self._deobfuscate_webcrack(js_code)
                if result["success"]:
                    return self._success_result(result)

            # 方法 3: 使用内置 AST 反混淆
            result = await self._deobfuscate_builtin(js_code)
            if result["success"]:
                return self._success_result(result)

            # 如果都失败，返回原始代码并标记
            return self._success_result({
                "deobfuscated_code": js_code,
                "detected_type": "unknown",
                "method_used": "none",
                "success": True,
                "warning": "未能反混淆，返回原始代码",
            })

        except Exception as exc:
            log.error("deobfuscate_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"反混淆失败: {exc}",
            )

    async def _deobfuscate_by_type(self, js_code: str, obfuscator_type: str) -> dict:
        """根据已知混淆器类型反混淆"""
        log.info("deobfuscate_by_type", type=obfuscator_type)

        if "obfuscator.io" in obfuscator_type.lower() or "javascript-obfuscator" in obfuscator_type.lower():
            return await self._deobfuscate_obfuscator_io(js_code)

        if "webpack" in obfuscator_type.lower() or "browserify" in obfuscator_type.lower():
            return await self._deobfuscate_webpack(js_code)

        # 未知类型，使用通用方法
        return await self._deobfuscate_builtin(js_code)

    async def _deobfuscate_webcrack(self, js_code: str) -> dict:
        """使用 webcrack 反混淆"""
        log.info("deobfuscate_webcrack_attempt")

        # 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(js_code)
            temp_path = f.name

        try:
            # 运行 webcrack
            cmd = [str(self._webcrack_path), temp_path]
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
                text=True,
            )

            if result.returncode == 0 and result.stdout:
                # 读取输出
                output_file = temp_path.replace(".js", ".deobfuscated.js")
                if Path(output_file).exists():
                    deobfuscated = Path(output_file).read_text(encoding="utf-8")
                    return {
                        "deobfuscated_code": deobfuscated,
                        "detected_type": "detected_by_webcrack",
                        "method_used": "webcrack",
                        "success": True,
                    }

                # 如果没有输出文件，webcrack 可能输出了到 stdout
                if result.stdout:
                    return {
                        "deobfuscated_code": result.stdout,
                        "detected_type": "detected_by_webcrack",
                        "method_used": "webcrack",
                        "success": True,
                    }

            log.warning("webcrack_failed", stderr=result.stderr)
            return {"success": False}

        except subprocess.TimeoutExpired:
            log.error("webcrack_timeout")
            return {"success": False}
        except Exception as e:
            log.error("webcrack_error", error=str(e))
            return {"success": False}
        finally:
            # 清理临时文件
            try:
                Path(temp_path).unlink(missing_ok=True)
                Path(temp_path.replace(".js", ".deobfuscated.js")).unlink(missing_ok=True)
            except:
                pass

    async def _deobfuscate_obfuscator_io(self, js_code: str) -> dict:
        """反混淆 obfuscator.io 混淆的代码"""
        # 尝试识别混淆特征
        has_hex_vars = bool(re.search(r"_0x[a-f0-9]{4,}", js_code))
        has_string_array = bool(re.search(r"var\s+_0x[a-f0-9]+\s*=\s*\[[\'\"]", js_code))
        has_control_flow = bool(re.search(r"switch\s*\(\s*_0x[a-f0-9]+\s*\)", js_code))

        detected = []
        if has_hex_vars:
            detected.append("hex_variables")
        if has_string_array:
            detected.append("string_array")
        if has_control_flow:
            detected.append("control_flow_flattening")

        log.info("obfuscator_io_detected", features=detected)

        # 使用内置方法处理
        return await self._deobfuscate_builtin(js_code, features=detected)

    async def _deobfuscate_webpack(self, js_code: str) -> dict:
        """反混淆 webpack 打包的代码"""
        # 尝试识别 webpack 特征
        has_webpack_require = bool(re.search(r"__webpack_require__", js_code))
        has_module_exports = bool(re.search(r"module\.exports\s*=", js_code))
        has_webpack_jsonp = bool(re.search(r"webpackJsonp", js_code))

        detected = []
        if has_webpack_require:
            detected.append("webpack_require")
        if has_module_exports:
            detected.append("module_exports")
        if has_webpack_jsonp:
            detected.append("webpack_jsonp")

        log.info("webpack_detected", features=detected)

        # webpack 通常需要 unpacker，不是简单的反混淆
        # 返回原始代码，标记为 webpack
        return {
            "deobfuscated_code": js_code,
            "detected_type": "webpack",
            "method_used": "detection_only",
            "success": True,
            "note": "webpack 打包代码需要 unpacker 处理",
        }

    async def _deobfuscate_builtin(self, js_code: str, features: list = None) -> dict:
        """使用内置 AST 方法反混淆"""
        log.info("deobfuscate_builtin_attempt", has_advanced=HAS_ADVANCED)

        if features is None:
            features = []

        # 优先尝试高级反混淆器
        if HAS_ADVANCED and ("string_array" in features or "hex_variables" in features):
            try:
                log.info("trying_advanced_deobfuscator")
                advanced_result = advanced_deobfuscate(js_code)
                
                return {
                    "deobfuscated_code": advanced_result.get("code", js_code),
                    "detected_type": "advanced_ast",
                    "method_used": "advanced_deobfuscator",
                    "success": True,
                    "improvement": advanced_result.get("improvement", {}),
                    "techniques": advanced_result.get("techniques_used", []),
                }
            except Exception as e:
                log.warning("advanced_deobfuscator_failed", error=str(e))
                # 回退到基本方法

        # 基本处理
        result = js_code

        # 1. 移除常见的反调试代码
        result = self._remove_anti_debug(result)

        # 2. 解码字符串数组 (如果有)
        if "string_array" in features:
            result = self._decode_string_arrays(result)

        # 3. 恢复十六进制变量名
        if "hex_variables" in features:
            result = self._restore_hex_variables(result)

        # 4. 简化控制流
        if "control_flow_flattening" in features:
            result = self._simplify_control_flow(result)

        # 5. 美化代码
        result = self._prettify(result)

        # 检测反混淆后的代码质量
        original_entropy = self._calculate_entropy(js_code)
        result_entropy = self._calculate_entropy(result)
        entropy_reduction = (original_entropy - result_entropy) / original_entropy * 100 if original_entropy > 0 else 0

        log.info("deobfuscate_builtin_result",
            original_entropy=original_entropy,
            result_entropy=result_entropy,
            entropy_reduction=entropy_reduction,
        )

        return {
            "deobfuscated_code": result,
            "detected_type": "builtin_ast",
            "method_used": "builtin",
            "success": True,
            "entropy_reduction": entropy_reduction,
        }

    def _remove_anti_debug(self, code: str) -> str:
        """移除反调试代码"""
        patterns = [
            # Debugger 检测
            r"if\s*\(\s*typeof\s+debug\s*!==\s*['\"]undefined['\"]\s*\)\s*;?\s*debugger;",
            r"while\s*\(\s*true\s*\)\s*\{\s*debugger\s*;?\s*\}",
            # Console 检测
            r"if\s*\(\s*window\.console\s*\)\s*\{[^}]*console\.log\s*\([^)]*\)[^}]*\}",
            # Function 检测
            r"function\s+\w+\s*\(\s*\)\s*\{\s*debugger\s*;?\s*\}",
        ]

        for pattern in patterns:
            code = re.sub(pattern, "", code, flags=re.IGNORECASE | re.MULTILINE)

        return code

    def _decode_string_arrays(self, code: str) -> str:
        """解码字符串数组"""
        # 查找字符串数组声明
        # 例如: var _0x1a2b = ["hello", "world", "test"];
        array_pattern = r'var\s+(_0x[a-f0-9]+)\s*=\s*\[([^\]]+)\]'
        
        matches = re.findall(array_pattern, code)
        
        for var_name, strings in matches:
            # 解析字符串
            string_list = re.findall(r'"([^"]*)"', strings)
            
            # 替换数组访问
            # 例如: _0x1a2b[0] -> "hello"
            for i, s in enumerate(string_list):
                code = code.replace(f'{var_name}[{i}]', f'"{s}"')
        
        return code

    def _restore_hex_variables(self, code: str) -> str:
        """恢复十六进制变量名为可读名称"""
        # 这是一个简化版本，真正实现需要 AST 分析
        # 查找使用模式
        
        # 例如将 _0x1234 重命名为更有意义的名称
        hex_vars = re.findall(r'_0x([a-f0-9]{4,})', code)
        unique_vars = list(set(hex_vars))[:20]  # 限制数量
        
        for i, var in enumerate(unique_vars):
            code = re.sub(
                rf'\b_0x{var}\b',
                f'_var_{i}',
                code
            )
        
        return code

    def _simplify_control_flow(self, code: str) -> str:
        """简化控制流平坦化"""
        # 这是一个简化的实现
        # 真正的实现需要 AST 级别的分析
        
        # 移除空的 switch 语句
        code = re.sub(r'switch\s*\([^)]+\)\s*\{\s*\}', '', code)
        
        # 简化死代码
        code = re.sub(r'if\s*\(\s*false\s*\)\s*\{[^}]*\}', '', code)
        
        return code

    def _prettify(self, code: str) -> str:
        """美化代码 (简化版本)"""
        # 添加适当的缩进
        lines = code.split("\n")
        result = []
        indent = 0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 减少缩进
            if line.startswith("}") or line.startswith("]"):
                indent = max(0, indent - 1)
            
            result.append("  " * indent + line)
            
            # 增加缩进
            if line.endswith("{") or line.endswith("["):
                indent += 1
            elif line.endswith(":"):  # case 语句
                indent += 1
        
        return "\n".join(result)

    def _calculate_entropy(self, code: str) -> float:
        """计算代码的信息熵"""
        if not code:
            return 0
        
        # 简单的字符频率熵
        from collections import Counter
        import math
        counter = Counter(code)
        total = len(code)
        
        entropy = 0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        
        return entropy

    def _success_result(self, result: dict) -> ToolResult:
        """创建成功的结果"""
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output={
                "deobfuscated_code": result.get("deobfuscated_code", ""),
                "detected_type": result.get("detected_type", "unknown"),
                "method_used": result.get("method_used", "unknown"),
                "success": True,
                "warning": result.get("warning", ""),
                "note": result.get("note", ""),
            },
        )


# 注册工具
try:
    from axelo.tools.base import get_registry
    get_registry().register(DeobfuscateTool())
    log.info("deobfuscate_tool_registered")
except Exception as e:
    log.warning("deobfuscate_tool_register_failed", error=str(e))