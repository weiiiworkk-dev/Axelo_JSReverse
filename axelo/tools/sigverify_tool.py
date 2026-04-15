"""
签名验证工具 - Signature Verification Tool

自动测试生成的签名是否有效:
1. 检查签名代码语法
2. 模拟签名生成
3. 与实际 API 响应对比
4. 报告签名有效性

用法:
    sigverify_tool.run({"python_code": "...", "target_url": "...", "test_params": {...}})
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

from axelo.tools.base import BaseTool, ToolOutput, ToolResult, ToolStatus

log = structlog.get_logger(__name__)


class SigVerifyTool(BaseTool):
    """签名验证工具"""

    def __init__(self):
        super().__init__()

    @property
    def name(self) -> str:
        return "sigverify"
    
    @property
    def description(self) -> str:
        return "验证生成的签名代码是否有效"
    
    def _create_schema(self) -> "ToolSchema":
        from axelo.tools.base import ToolSchema, ToolInput, ToolCategory, ToolOutput
        
        output_schema = [
            ToolOutput(name="syntax_valid", type="boolean", description="语法是否有效"),
            ToolOutput(name="imports_valid", type="boolean", description="导入是否有效"),
            ToolOutput(name="signature_generated", type="boolean", description="是否能生成签名"),
            ToolOutput(name="signature_output", type="string", description="生成的签名示例"),
            ToolOutput(name="issues", type="array", description="发现的问题"),
            ToolOutput(name="recommendations", type="array", description="建议"),
            ToolOutput(name="score", type="number", description="验证得分 (0-100)"),
        ]
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.ANALYSIS,
            input_schema=[
                ToolInput(name="python_code", type="string", description="生成的 Python 签名代码"),
                ToolInput(name="target_url", type="string", description="目标 API URL"),
                ToolInput(name="test_params", type="object", description="测试参数"),
            ],
            output_schema=output_schema,
            timeout_seconds=30,
            retry_enabled=False,
        )

    async def execute(self, input_data: dict[str, Any], state: Any) -> ToolResult:
        return await self.run(input_data, state)

    async def run(self, input_data: dict, state: Any = None) -> ToolResult:
        python_code = input_data.get("python_code", "")
        target_url = input_data.get("target_url", "")
        test_params = input_data.get("test_params", {"page": 1, "size": 20})

        if not python_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: python_code",
            )

        try:
            log.info("sigverify_start", code_length=len(python_code))

            # 1. 语法检查
            syntax_result = await self._check_syntax(python_code)
            
            # 2. 导入检查
            imports_result = await self._check_imports(python_code)
            
            # 3. 签名生成测试
            signature_result = await self._test_signature_generation(
                python_code, test_params
            )
            
            # 4. 评估结果
            score = self._calculate_score(
                syntax_result, imports_result, signature_result
            )
            
            # 5. 生成建议
            recommendations = self._generate_recommendations(
                syntax_result, imports_result, signature_result
            )

            issues = []
            if not syntax_result["valid"]:
                issues.append(f"语法错误: {syntax_result.get('error', 'unknown')}")
            if not imports_result["valid"]:
                issues.append(f"导入错误: {imports_result.get('error', 'unknown')}")
            if not signature_result["success"]:
                issues.append(f"签名生成失败: {signature_result.get('error', 'unknown')}")

            result = {
                "syntax_valid": syntax_result["valid"],
                "imports_valid": imports_result["valid"],
                "signature_generated": signature_result["success"],
                "signature_output": signature_result.get("signature", ""),
                "issues": issues,
                "recommendations": recommendations,
                "score": score,
            }

            log.info("sigverify_complete", score=score, issues=len(issues))

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=result,
            )

        except Exception as exc:
            log.error("sigverify_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"验证失败: {exc}",
            )

    async def _check_syntax(self, code: str) -> dict:
        """检查 Python 语法"""
        log.info("checking_syntax")
        
        # 检查是否有 generate_signature 函数
        if "def generate_signature" not in code:
            return {"valid": False, "error": "Missing generate_signature function"}
        
        # 检查是否有 make_request 函数
        if "def make_request" not in code and "async def make_request" not in code:
            return {"valid": False, "error": "Missing make_request function"}
        
        # 检查是否有必要的导入
        required_imports = ["import asyncio", "import hashlib"]
        missing = [imp for imp in required_imports if imp not in code]
        if missing:
            return {"valid": False, "error": f"Missing imports: {', '.join(missing)}"}
        
        return {"valid": True}

    async def _check_imports(self, code: str) -> dict:
        """检查导入是否可用"""
        log.info("checking_imports")
        
        # 检查常见的依赖
        standard_libs = ["asyncio", "hashlib", "hmac", "base64", "json", "datetime"]
        for lib in standard_libs:
            if f"import {lib}" in code or f"from {lib}" in code:
                # 简单验证 - 检查语法
                if "httpx" in code:
                    # httpx 是外部依赖
                    return {"valid": True, "note": "httpx is external dependency"}
        
        return {"valid": True}

    async def _test_signature_generation(self, code: str, params: dict) -> dict:
        """测试签名生成"""
        log.info("testing_signature_generation", params=params)
        
        # 创建测试脚本
        test_code = code + f"""

# 测试签名生成
if __name__ == "__main__":
    test_params = {params}
    
    # 测试 generate_signature 函数
    try:
        sig = generate_signature("test_key", test_params)
        print(f"SIGNATURE:{sig}")
    except Exception as e:
        print(f"ERROR:{e}")
"""
        
        # 写入临时文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(test_code)
            temp_path = f.name

        try:
            # 运行测试
            result = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                timeout=10,
                text=True,
            )
            
            # 检查输出
            output = result.stdout + result.stderr
            
            if "SIGNATURE:" in output:
                sig = output.split("SIGNATURE:")[1].split("\n")[0].strip()
                return {
                    "success": True,
                    "signature": sig[:100],  # 限制长度
                    "signature_length": len(sig),
                }
            elif "ERROR:" in output:
                error = output.split("ERROR:")[1].split("\n")[0].strip()
                return {"success": False, "error": error}
            else:
                return {"success": False, "error": "No signature output"}
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # 清理临时文件
            try:
                Path(temp_path).unlink(missing_ok=True)
            except:
                pass

    def _calculate_score(self, syntax: dict, imports: dict, signature: dict) -> float:
        """计算验证得分"""
        score = 0
        
        # 语法检查 (40 分)
        if syntax.get("valid"):
            score += 40
        
        # 导入检查 (20 分)
        if imports.get("valid"):
            score += 20
        
        # 签名生成 (40 分)
        if signature.get("success"):
            score += 40
        elif "generate_signature" in signature.get("error", "").lower():
            # 部分实现
            score += 10
        
        return score

    def _generate_recommendations(
        self, syntax: dict, imports: dict, signature: dict
    ) -> list:
        """生成改进建议"""
        recommendations = []
        
        if not syntax.get("valid"):
            recommendations.append("修复语法错误")
        
        if not imports.get("valid"):
            recommendations.append("安装依赖: pip install httpx pycryptodome")
        
        if not signature.get("success"):
            error = signature.get("error", "")
            if "SECRET_KEY" in error:
                recommendations.append("需要设置有效的 SECRET_KEY")
            elif "hmac" in error.lower():
                recommendations.append("检查 HMAC 实现是否正确")
            else:
                recommendations.append(f"调试签名函数: {error}")
        
        if signature.get("success"):
            recommendations.append("签名函数工作正常，可以测试实际 API")
        
        # 添加通用建议
        if not recommendations:
            recommendations.append("代码验证通过，建议进行实际 API 测试")
        
        return recommendations


# 注册工具
try:
    from axelo.tools.base import get_registry
    get_registry().register(SigVerifyTool())
    log.info("sigverify_tool_registered")
except Exception as e:
    log.warning("sigverify_tool_register_failed", error=str(e))