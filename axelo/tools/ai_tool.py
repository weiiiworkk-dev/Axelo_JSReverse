"""
AI Tool - AI 分析工具

集成 DeepSeek API 进行签名假设生成
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog
import httpx

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


@dataclass
class AIAnalysisOutput:
    """AI 分析输出"""
    hypothesis: str = ""
    signature_type: str = ""
    algorithm: str = ""
    key_location: str = ""
    confidence: float = 0.0
    reasoning: str = ""


class AITool(BaseTool):
    """AI 分析工具 - 签名假设生成"""
    
    def __init__(self):
        super().__init__()
        self._client = None
    
    @property
    def name(self) -> str:
        return "ai_analyze"
    
    @property
    def description(self) -> str:
        return "AI 分析：根据分析结果生成签名假设"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.AI,
            input_schema=[
                ToolInput(
                    name="candidates",
                    type="array",
                    description="签名候选",
                    required=True,
                ),
                ToolInput(
                    name="crypto_usage",
                    type="array",
                    description="加密使用情况",
                    required=False,
                ),
                ToolInput(
                    name="goal",
                    type="string",
                    description="爬取目标",
                    required=True,
                ),
                ToolInput(
                    name="js_code",
                    type="string",
                    description="JavaScript 代码片段",
                    required=False,
                ),
                ToolInput(
                    name="context",
                    type="object",
                    description="额外上下文",
                    required=False,
                    default={},
                ),
                ToolInput(
                    name="dynamic_analysis",
                    type="object",
                    description="动态分析结果 (API调用追踪、签名函数调用)",
                    required=False,
                    default={},
                ),
                ToolInput(
                    name="signature_extraction",
                    type="object",
                    description="签名提取结果 (密钥、算法)",
                    required=False,
                    default={},
                ),
            ],
            output_schema=[
                ToolOutput(name="hypothesis", type="string", description="假设描述"),
                ToolOutput(name="signature_type", type="string", description="签名类型"),
                ToolOutput(name="algorithm", type="string", description="算法"),
                ToolOutput(name="key_location", type="string", description="密钥位置"),
                ToolOutput(name="confidence", type="number", description="置信度"),
                ToolOutput(name="reasoning", type="string", description="推理过程"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        """执行 AI 分析"""
        candidates = input_data.get("candidates") or input_data.get("signature_candidates") or []
        crypto_usage = input_data.get("crypto_usage") or []
        api_endpoints = input_data.get("api_endpoints") or input_data.get("endpoints") or []
        goal = input_data.get("goal") or ""
        
        # 提取动态分析结果
        dynamic_analysis = input_data.get("dynamic_analysis") or {}
        
        # 提取签名提取结果
        signature_extraction = input_data.get("signature_extraction") or {}
        
        if not goal:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: goal",
            )
        
        try:
            # 调用 AI 生成假设
            output = await self._generate_analysis(input_data, state)
            
            # 将 API 端点信息也放入输出
            # 如果有动态分析或签名提取结果，提高置信度
            confidence = output.confidence
            if dynamic_analysis and dynamic_analysis.get("has_signatures"):
                confidence = min(confidence + 0.15, 1.0)
            if signature_extraction and signature_extraction.get("key_value"):
                confidence = min(confidence + 0.25, 1.0)
            
            output_data = {
                "hypothesis": output.hypothesis,
                "signature_type": output.signature_type,
                "algorithm": output.algorithm,
                "key_location": output.key_location,
                "confidence": confidence,
                "reasoning": output.reasoning,
                "api_endpoints": api_endpoints,  # 传递端点信息
                "dynamic_analysis": dynamic_analysis,  # 传递动态分析结果
                "signature_extraction": signature_extraction,  # 传递签名提取结果
            }
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=output_data,
            )
            
        except Exception as exc:
            log.error("ai_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    async def _generate_analysis(self, input_data: dict, state: ToolState) -> AIAnalysisOutput:
        """执行 AI 分析"""
        candidates = input_data.get("candidates") or input_data.get("signature_candidates") or []
        crypto_usage = input_data.get("crypto_usage") or []
        # 新增: 提取 API 端点
        api_endpoints = input_data.get("api_endpoints") or input_data.get("endpoints") or []
        goal = input_data.get("goal") or ""
        js_code = input_data.get("js_code") or input_data.get("content") or ""
        
        # 处理 bundles 列表
        if not js_code and "bundles" in input_data:
            bundles = input_data["bundles"]
            if isinstance(bundles, list):
                js_code = "\n\n".join([b.get("content", "") for b in bundles[:3]])
        
        # 获取动态分析和签名提取结果
        dynamic_analysis = input_data.get("dynamic_analysis") or {}
        signature_extraction = input_data.get("signature_extraction") or {}
        
        try:
            # 构建 prompt (带动态分析信息)
            prompt = self._build_prompt(
                candidates, crypto_usage, api_endpoints, goal, js_code,
                dynamic_analysis=dynamic_analysis,
                signature_extraction=signature_extraction
            )
            deepseek_api_key = settings.deepseek_api_key
            
            log.info("ai_analyze_check", has_api_key=bool(deepseek_api_key), key_length=len(deepseek_api_key))
            
            if not deepseek_api_key:
                return self._fallback_analysis(input_data)
            
            output = await self._call_deepseek(prompt, deepseek_api_key)
            output.api_endpoints = api_endpoints  # 传递端点信息
            
            return output
        except Exception as exc:
            log.warning("ai_analyze_failed_falling_back", error=str(exc), exc_info=True)
            return self._fallback_analysis(input_data)
    
    def _fallback_analysis(self, input_data: dict) -> AIAnalysisOutput:
        """降级分析 - 基于规则的启发式分析"""
        candidates = input_data.get("candidates") or input_data.get("signature_candidates") or []
        crypto_usage = input_data.get("crypto_usage", [])
        goal = input_data.get("goal", "")
        
        output = AIAnalysisOutput()
        
        # 从加密使用中提取算法
        if crypto_usage:
            algos = [c.get("algorithm") for c in crypto_usage if c.get("detected")]
            if algos:
                output.algorithm = ", ".join(algos)
                output.confidence = 0.6
        
        # 从候选中提取签名类型 - 只有在找到相关类型时才设置
        output.signature_type = ""
        if candidates:
            for c in candidates[:5]:
                ctype = c.get("type", "")
                if ctype in ["sign", "signature", "hash", "hmac"]:
                    output.signature_type = ctype.upper()
                    break
        
        # 生成假设
        if output.algorithm:
            output.hypothesis = f"使用 {output.algorithm} 算法进行请求签名"
        else:
            output.hypothesis = "可能使用自定义签名算法，需要进一步分析"
        
        output.reasoning = f"基于 {len(candidates)} 个候选和 {len(crypto_usage)} 个加密使用进行分析"
        
        return output
    
    def _build_prompt(self, candidates, crypto_usage, api_endpoints, goal, js_code, dynamic_analysis=None, signature_extraction=None) -> str:
        """构建分析 prompt"""
        endpoints_str = "\n".join(api_endpoints[:10]) if api_endpoints else "无"
        
        # 添加动态分析信息
        dynamic_info = ""
        if dynamic_analysis:
            api_calls = dynamic_analysis.get("api_calls", [])
            sig_calls = dynamic_analysis.get("signature_calls", [])
            if api_calls:
                dynamic_info += "\n## 动态分析 - API 调用 (浏览器执行追踪)\n"
                for call in api_calls[:5]:
                    dynamic_info += f"- {call.get('method', 'GET')} {call.get('url', '')}\n"
            if sig_calls:
                dynamic_info += "\n## 动态分析 - 签名函数调用\n"
                for sig in sig_calls:
                    dynamic_info += f"- {sig.get('function', '')}: {sig.get('args', '')}\n"
        
        # 添加签名提取信息
        sig_extract_info = ""
        if signature_extraction:
            key_value = signature_extraction.get("key_value")
            algorithm = signature_extraction.get("algorithm")
            key_source = signature_extraction.get("key_source")
            if key_value:
                sig_extract_info += f"\n## 签名提取结果 (从JS静态分析)\n"
                sig_extract_info += f"- 密钥来源: {key_source}\n"
                sig_extract_info += f"- 密钥值: {key_value[:20]}...\n"
                sig_extract_info += f"- 算法: {algorithm}\n"
        
        prompt = f"""你是一个专业的 JavaScript 逆向工程师。请分析以下信息并生成签名假设。

## 爬取目标
{goal}

## 检测到的 API 端点 (从静态分析提取)
{endpoints_str}

## 签名候选 (从静态分析提取)
{json.dumps(candidates[:10], indent=2, ensure_ascii=False)}

## 加密使用 (从加密分析提取)
{json.dumps(crypto_usage, indent=2, ensure_ascii=False)}
{dynamic_info}
{sig_extract_info}
## JavaScript 代码片段
```javascript
{js_code[:2000]}
```

请分析并返回 JSON 格式的签名假设：
```json
{{
  "hypothesis": "假设描述",
  "signature_type": "签名类型 (如: HMAC, AES, RSA, 自定义)",
  "algorithm": "具体算法 (如: SHA256, AES-128-CBC)",
  "key_location": "密钥位置描述",
  "confidence": 0.0-1.0,
  "reasoning": "推理过程"
}}
```

只返回 JSON，不要其他内容。"""
        return prompt
    
    async def _call_deepseek(self, prompt: str, api_key: str) -> AIAnalysisOutput:
        """调用 DeepSeek API"""
        endpoint = "https://api.deepseek.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a professional JavaScript reverse engineering assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1000,
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            # 尝试解析 JSON
            try:
                # 提取 JSON 部分
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0]
                else:
                    json_str = content
                
                result = json.loads(json_str.strip())
                
                return AIAnalysisOutput(
                    hypothesis=result.get("hypothesis", ""),
                    signature_type=result.get("signature_type", ""),
                    algorithm=result.get("algorithm", ""),
                    key_location=result.get("key_location", ""),
                    confidence=result.get("confidence", 0.5),
                    reasoning=result.get("reasoning", ""),
                )
            except (json.JSONDecodeError, KeyError):
                pass
            
            # 如果解析失败，返回默认结果
            return AIAnalysisOutput(
                hypothesis=content[:200],
                confidence=0.3,
                reasoning="API 返回无法解析，使用原始响应",
            )


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(AITool())