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
        candidates = input_data.get("candidates", [])
        goal = input_data.get("goal")
        
        if not candidates:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: candidates",
            )
        
        if not goal:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: goal",
            )
        
        try:
            # 调用 AI 生成假设
            output = await self._analyze(input_data, state)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "hypothesis": output.hypothesis,
                    "signature_type": output.signature_type,
                    "algorithm": output.algorithm,
                    "key_location": output.key_location,
                    "confidence": output.confidence,
                    "reasoning": output.reasoning,
                },
            )
            
        except Exception as exc:
            log.error("ai_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )
    
    async def _analyze(self, input_data: dict, state: ToolState) -> AIAnalysisOutput:
        """调用 AI 进行分析"""
        candidates = input_data.get("candidates", [])
        goal = input_data.get("goal", "")
        crypto_usage = input_data.get("crypto_usage", [])
        js_code = input_data.get("js_code", "")[:2000]  # 限制代码长度
        
        # 检查是否有 DeepSeek API key
        api_key = getattr(settings, "deepseek_api_key", None) or getattr(settings, "anthropic_api_key", None)
        
        if not api_key:
            log.warning("no_ai_api_key", using_fallback=True)
            return self._fallback_analysis(input_data)
        
        # 构建 prompt
        prompt = self._build_prompt(candidates, crypto_usage, goal, js_code)
        
        try:
            # 尝试使用 DeepSeek
            output = await self._call_deepseek(prompt, api_key)
            return output
        except Exception as e:
            log.warning("ai_api_failed", error=str(e), using_fallback=True)
            return self._fallback_analysis(input_data)
    
    def _build_prompt(self, candidates, crypto_usage, goal, js_code) -> str:
        """构建分析 prompt"""
        prompt = f"""你是一个专业的 JavaScript 逆向工程师。请分析以下信息并生成签名假设。

## 爬取目标
{goal}

## 签名候选 (从静态分析提取)
{json.dumps(candidates[:10], indent=2, ensure_ascii=False)}

## 加密使用 (从加密分析提取)
{json.dumps(crypto_usage, indent=2, ensure_ascii=False)}

## JavaScript 代码片段
```javascript
{js_code[:1500]}
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
        # DeepSeek API endpoint
        endpoint = "https://api.deepseek.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are a professional JavaScript reverse engineering assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        }
        
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 解析 JSON 响应
            try:
                # 提取 JSON
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    data = json.loads(json_str)
                    
                    return AIAnalysisOutput(
                        hypothesis=data.get("hypothesis", ""),
                        signature_type=data.get("signature_type", ""),
                        algorithm=data.get("algorithm", ""),
                        key_location=data.get("key_location", ""),
                        confidence=float(data.get("confidence", 0.5)),
                        reasoning=data.get("reasoning", ""),
                    )
            except json.JSONDecodeError:
                pass
            
            # 如果解析失败，返回默认结果
            return AIAnalysisOutput(
                hypothesis=content[:200],
                confidence=0.3,
                reasoning="API 返回无法解析，使用原始响应",
            )
    
    def _fallback_analysis(self, input_data: dict) -> AIAnalysisOutput:
        """降级分析 - 基于规则的启发式分析"""
        candidates = input_data.get("candidates", [])
        crypto_usage = input_data.get("crypto_usage", [])
        goal = input_data.get("goal", "")
        
        output = AIAnalysisOutput()
        
        # 从加密使用中提取算法
        if crypto_usage:
            algos = [c.get("algorithm") for c in crypto_usage if c.get("detected")]
            if algos:
                output.algorithm = ", ".join(algos)
                output.confidence = 0.6
        
        # 从候选中提取签名类型
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


# 注册工具
from axelo.tools.base import get_registry

get_registry().register(AITool())