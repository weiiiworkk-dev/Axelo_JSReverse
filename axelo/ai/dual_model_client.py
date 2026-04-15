"""DeepSeek-only execution client."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Optional
from urllib import request
import urllib.error
import structlog

log = structlog.get_logger()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    api_url: str
    api_key: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 60


@dataclass
class ChatMessage:
    """Chat message."""
    role: str
    content: str


@dataclass
class ChatResponse:
    """Chat response from model."""
    content: str
    model: str
    tokens_used: int = 0
    finish_reason: str = ""
    raw_response: dict | None = None


@dataclass
class ExecutionResult:
    """Final execution result."""
    success: bool
    content: str = ""
    code: str = ""
    source: str = "deepseek"
    confidence: float = 0.0
    error: str = ""
    fallback: bool = False
    cost: float = 0.0  # USD


# =============================================================================
# BASE CLIENT (Sync)
# =============================================================================

class BaseAPIClient:
    """Base class for API clients (synchronous)."""
    
    def __init__(self, config: ModelConfig):
        self._config = config
    
    def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Send chat request."""
        raise NotImplementedError
    
    def _make_request(self, payload: dict) -> dict:
        """Make API request using urllib."""
        
        headers = self._get_headers()
        
        req = request.Request(
            self._config.api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        try:
            with request.urlopen(req, timeout=self._config.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            log.error("http_error", status=e.code, error=error_body)
            raise Exception(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            log.error("url_error", error=str(e))
            raise Exception(f"URL error: {str(e)}")
    
    def _get_headers(self) -> dict:
        """Get API headers."""
        raise NotImplementedError


# =============================================================================
# DEEPSEEK CLIENT (Reasoning)
# =============================================================================

class DeepSeekClient(BaseAPIClient):
    """
    DeepSeek R1 reasoning model client.
    
    API: https://platform.deepseek.com/
    Model: deepseek-reasoner
    """
    
    def __init__(self, api_key: str = ""):
        config = ModelConfig(
            name="deepseek-reasoner",
            api_url="https://api.deepseek.com/v1/chat/completions",
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            max_tokens=4096,
            temperature=0.7,
            timeout=60,
        )
        super().__init__(config)
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
    
    def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Send chat request to DeepSeek."""
        
        payload = {
            "model": self._config.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "temperature": kwargs.get("temperature", self._config.temperature),
        }
        
        try:
            response = self._make_request(payload)
            
            return ChatResponse(
                content=response["choices"][0]["message"]["content"],
                model=self._config.name,
                tokens_used=response.get("usage", {}).get("total_tokens", 0),
                finish_reason=response["choices"][0].get("finish_reason", ""),
                raw_response=response,
            )
        except Exception as e:
            log.error("deepseek_r1_request_failed", error=str(e))
            raise


# =============================================================================
# DEEPSEEK V3 CLIENT (Primary Model)
# =============================================================================

class DeepSeekV3Client(BaseAPIClient):
    """
    DeepSeek V3 general purpose model client.
    
    API: https://platform.deepseek.com/
    Model: deepseek-chat (V3)
    
    Priority: Primary (first choice)
    """
    
    def __init__(self, api_key: str = ""):
        config = ModelConfig(
            name="deepseek-chat",
            api_url="https://api.deepseek.com/v1/chat/completions",
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""),
            max_tokens=4096,
            temperature=0.7,
            timeout=60,
        )
        super().__init__(config)
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
    
    def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Send chat request to DeepSeek V3."""
        
        payload = {
            "model": self._config.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": kwargs.get("max_tokens", self._config.max_tokens),
            "temperature": kwargs.get("temperature", self._config.temperature),
        }
        
        try:
            response = self._make_request(payload)
            
            return ChatResponse(
                content=response["choices"][0]["message"]["content"],
                model=self._config.name,
                tokens_used=response.get("usage", {}).get("total_tokens", 0),
                finish_reason=response["choices"][0].get("finish_reason", ""),
                raw_response=response,
            )
        except Exception as e:
            log.error("deepseek_v3_request_failed", error=str(e))
            raise


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class DeepSeekExecutionClient:
    """
    Unified DeepSeek orchestration with optional R1 fallback.
    """
    
    def __init__(
        self,
        deepseek_key: str = "",
        enable_fallback: bool = True,
    ):
        self._deepseek_v3 = None
        self._deepseek_r1 = None
        
        # Initialize DeepSeek V3 (Primary)
        if deepseek_key or os.getenv("DEEPSEEK_API_KEY"):
            try:
                self._deepseek_v3 = DeepSeekV3Client(deepseek_key)
                log.info("deepseek_v3_client_initialized_primary")
            except Exception as e:
                log.warning("deepseek_v3_init_failed", error=str(e))
        
        # Initialize DeepSeek R1 (Secondary - for reasoning)
        if deepseek_key or os.getenv("DEEPSEEK_API_KEY"):
            try:
                self._deepseek_r1 = DeepSeekClient(deepseek_key)
                log.info("deepseek_r1_client_initialized_secondary")
            except Exception as e:
                log.warning("deepseek_r1_init_failed", error=str(e))
        
        self._enable_fallback = enable_fallback
        
        log.info("deepseek_execution_client_initialized",
                deepseek_v3=bool(self._deepseek_v3),
                deepseek_r1=bool(self._deepseek_r1))
    
    def execute(
        self,
        prompt: str,
        task_type: str = "hybrid",
        reasoning_context: str = "",
        **kwargs
    ) -> ExecutionResult:
        """
        Execute task with automatic model fallback.
        
        Priority Chain: V3 → R1
        
        Args:
            prompt: Main prompt
            task_type: "reasoning_only", "coding_only", "hybrid"
            reasoning_context: Context from reasoning for coding
            **kwargs: Additional parameters
            
        Returns:
            ExecutionResult
        """
        
        # Step 1: Try DeepSeek V3 (Primary)
        if self._deepseek_v3:
            try:
                return self._execute_with_v3(prompt, task_type, reasoning_context, **kwargs)
            except Exception as e:
                log.warning("deepseek_v3_execution_failed", error=str(e))
                # Continue to Step 2
        
        # Step 2: Try DeepSeek R1 (Secondary)
        if self._deepseek_r1:
            try:
                return self._execute_with_r1(prompt, task_type, reasoning_context, **kwargs)
            except Exception as e:
                log.warning("deepseek_r1_execution_failed", error=str(e))
                # Continue to Step 3
        
        return ExecutionResult(
            success=False,
            error="No DeepSeek models available. Please configure API keys.",
            source="none",
        )
    
    def _execute_with_v3(
        self,
        prompt: str,
        task_type: str,
        reasoning_context: str,
        **kwargs
    ) -> ExecutionResult:
        """Execute using DeepSeek V3."""
        
        try:
            # Use DeepSeek V3 for both reasoning and coding
            if task_type in ("reasoning_only", "hybrid"):
                # Step 1: Reasoning (analyze JS)
                reasoning_result = self._run_reasoning_v3(prompt)
                reasoning_context = reasoning_result.content
                
                if task_type == "reasoning_only":
                    return ExecutionResult(
                        success=True,
                        content=reasoning_result.content,
                        source="deepseek_v3_reasoning",
                        confidence=0.90,
                    )
            
            # Step 2: Coding (generate code) - using DeepSeek V3
            coding_result = self._run_coding_with_v3(prompt, reasoning_context)
            
            # Validate result
            if self._validate_result(coding_result):
                return ExecutionResult(
                    success=True,
                    content=coding_result.content,
                    code=self._extract_code(coding_result.content),
                    source="deepseek_v3",
                    confidence=0.90,
                )
            else:
                raise ValueError("Invalid code generated")
                
        except Exception as e:
            log.warning("deepseek_v3_failed", error=str(e))
            raise
    
    def _execute_with_r1(
        self,
        prompt: str,
        task_type: str,
        reasoning_context: str,
        **kwargs
    ) -> ExecutionResult:
        """Execute using DeepSeek R1."""
        
        try:
            # Use DeepSeek R1 for both reasoning and coding
            if task_type in ("reasoning_only", "hybrid"):
                # Step 1: Reasoning (analyze JS)
                reasoning_result = self._run_reasoning(prompt)
                reasoning_context = reasoning_result.content
                
                if task_type == "reasoning_only":
                    return ExecutionResult(
                        success=True,
                        content=reasoning_result.content,
                        source="deepseek_r1_reasoning",
                        confidence=0.85,
                    )
            
            # Step 2: Coding (generate code) - using DeepSeek R1
            coding_result = self._run_coding_with_deepseek(prompt, reasoning_context)
            
            # Validate result
            if self._validate_result(coding_result):
                return ExecutionResult(
                    success=True,
                    content=coding_result.content,
                    code=self._extract_code(coding_result.content),
                    source="deepseek_r1",
                    confidence=0.85,
                )
            else:
                raise ValueError("Invalid code generated")
                
        except Exception as e:
            log.warning("deepseek_r1_failed", error=str(e))
            raise
            
            return ExecutionResult(
                success=False,
                error=str(e),
                source="deepseek",
            )
    
    def _run_reasoning(self, prompt: str) -> ChatResponse:
        """Run reasoning model."""
        
        system_prompt = """You are a professional reverse engineer specializing in JavaScript analysis.
Analyze the provided code and explain:
1. Signature generation logic
2. Encryption algorithms used
3. Key functions and data flow
4. Signature parameter locations"""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=prompt),
        ]
        
        return self._deepseek_r1.chat(messages)
    
    def _run_reasoning_v3(self, prompt: str) -> ChatResponse:
        """Run reasoning using DeepSeek V3."""
        
        system_prompt = """You are a professional reverse engineer specializing in JavaScript analysis.
Analyze the provided code and explain:
1. Signature generation logic
2. Encryption algorithms used
3. Key functions and data flow
4. Signature parameter locations"""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=prompt),
        ]
        
        return self._deepseek_v3.chat(messages)
    
    def _run_coding(self, prompt: str, context: str = "") -> ChatResponse:
        """Run coding model."""
        
        system_prompt = """You are a Python code generation expert.
Based on the analysis, generate clean, runnable signature generation code.
Output ONLY the code, no explanations."""

        user_content = prompt
        if context:
            user_content = f"Analysis:\n{context}\n\nTask:\n{prompt}"

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
        
        return self._deepseek_r1.chat(messages)
    
    def _run_coding_with_deepseek(self, prompt: str, context: str = "") -> ChatResponse:
        """Run coding using DeepSeek R1."""
        
        system_prompt = """You are both a reverse engineer AND a Python code expert.
Analyze JavaScript code AND generate complete, runnable Python signature generation code.

Output format:
```python
# Your generated code here
```

Include:
- Proper imports (hmac, hashlib, etc.)
- Signature generation function
- Main execution block
- Error handling"""

        user_content = prompt
        if context:
            user_content = f"Analysis Context:\n{context}\n\nTask:\n{prompt}"

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
        
        return self._deepseek_r1.chat(messages)
    
    def _run_coding_with_v3(self, prompt: str, context: str = "") -> ChatResponse:
        """Run coding using DeepSeek V3."""
        
        system_prompt = """You are both a reverse engineer AND a Python code expert.
Analyze JavaScript code AND generate complete, runnable Python signature generation code.

Output format:
```python
# Your generated code here
```

Include:
- Proper imports (hmac, hashlib, etc.)
- Signature generation function
- Main execution block
- Error handling"""

        user_content = prompt
        if context:
            user_content = f"Analysis Context:\n{context}\n\nTask:\n{prompt}"

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
        
        return self._deepseek_v3.chat(messages)
    
    def _validate_result(self, response: ChatResponse) -> bool:
        """Validate response quality."""
        
        content = response.content
        
        # Check if empty
        if not content or len(content) < 50:
            return False
        
        # Check for error indicators
        error_indicators = ["error", "failed", "cannot", "unable to"]
        if any(indicator in content.lower() for indicator in error_indicators):
            return False
        
        return True
    
    def _extract_code(self, content: str) -> str:
        """Extract code from response."""
        
        # Try to extract code block
        if "```python" in content:
            start = content.find("```python") + len("```python")
            end = content.find("```", start)
            if end > start:
                return content[start:end].strip()
        
        if "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end > start:
                return content[start:end].strip()
        
        # Return whole content if no code block
        return content


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_execution_client(
    deepseek_key: str = "",
) -> DeepSeekExecutionClient:
    """Create the DeepSeek execution client."""
    return DeepSeekExecutionClient(
        deepseek_key=deepseek_key,
    )


def quick_chat(
    prompt: str,
    model: str = "deepseek-chat",
    **kwargs
) -> ChatResponse:
    """Quick chat with DeepSeek models."""
    if model == "deepseek-reasoner":
        client = DeepSeekClient()
    else:
        client = DeepSeekV3Client()
    messages = [ChatMessage(role="user", content=prompt)]
    return client.chat(messages, **kwargs)
