"""Task router - classify and route tasks to appropriate models."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import structlog

log = structlog.get_logger()


class TaskType(Enum):
    """Task type classification."""
    REASONING_ONLY = "reasoning_only"  # 分析、理解、推理
    CODING_ONLY = "coding_only"        # 生成、代码、修复
    HYBRID = "hybrid"                  # 需要两者


@dataclass
class TaskClassification:
    """Task classification result."""
    task_type: TaskType
    reasoning_score: float  # 0-1
    coding_score: float     # 0-1
    confidence: float       # 0-1
    keywords_matched: list[str]


class TaskRouter:
    """
    Task router - classify and route tasks to appropriate models.
    
    分析任务内容，智能决定使用哪个模型：
    - 纯推理任务 → DeepSeek R1
    - 纯编码任务 → Qwen3-Coder
    - 混合任务 → 两个模型协作
    """
    
    # 推理关键词
    REASONING_KEYWORDS = [
        # 中文
        "分析", "推理", "理解", "追踪", "推导", "识别", "判断",
        "解释", "说明", "是什么", "为什么", "如何工作", "原理",
        # English
        "analyze", "analysis", "analyze", "understand", "trace",
        "identify", "recognize", "derive", "explain", "how does",
        "what is", "why", "reasoning", "logic", "pattern",
    ]
    
    # 编码关键词
    CODING_KEYWORDS = [
        # 中文
        "生成", "代码", "实现", "编写", "修复", "调试", "创建",
        "构建", "写", "生成代码", "实现功能", "编程",
        # English
        "generate", "code", "implement", "write", "create",
        "build", "fix", "debug", "program", "script",
        "function", "class", "module", "api", "python",
    ]
    
    # 优先级关键词 (强制使用特定模型)
    FORCE_REASONING = [
        "分析加密", "理解逻辑", "追踪数据流", "推导算法",
        "analyze encryption", "understand logic", "trace data flow",
    ]
    
    FORCE_CODING = [
        "生成代码", "写代码", "生成签名",
        "generate code", "write code", "generate signature",
    ]
    
    def __init__(self):
        self._reasoning_pattern = self._compile_pattern(self.REASONING_KEYWORDS)
        self._coding_pattern = self._compile_pattern(self.CODING_KEYWORDS)
    
    def _compile_pattern(self, keywords: list[str]) -> re.Pattern:
        """Compile keyword pattern."""
        escaped = [re.escape(kw) for kw in keywords]
        return re.compile("|".join(escaped), re.IGNORECASE)
    
    def classify(
        self,
        goal: str,
        description: str = "",
        js_code: str = "",
    ) -> TaskClassification:
        """
        Classify task type.
        
        Args:
            goal: Task goal
            description: Additional description
            js_code: JavaScript code (optional)
            
        Returns:
            TaskClassification
        """
        
        # Combine text for analysis
        combined = f"{goal} {description} {js_code[:500]}".lower()
        
        # Check force keywords first
        force_reasoning = any(kw in combined for kw in self.FORCE_REASONING)
        force_coding = any(kw in combined for kw in self.FORCE_CODING)
        
        if force_reasoning:
            return TaskClassification(
                task_type=TaskType.REASONING_ONLY,
                reasoning_score=1.0,
                coding_score=0.0,
                confidence=0.95,
                keywords_matched=["force_reasoning"],
            )
        
        if force_coding:
            return TaskClassification(
                task_type=TaskType.CODING_ONLY,
                reasoning_score=0.0,
                coding_score=1.0,
                confidence=0.95,
                keywords_matched=["force_coding"],
            )
        
        # Count keyword matches
        reasoning_matches = self._reasoning_pattern.findall(combined)
        coding_matches = self._coding_pattern.findall(combined)
        
        reasoning_count = len(reasoning_matches)
        coding_count = len(coding_matches)
        
        # Calculate scores
        total = reasoning_count + coding_count
        if total == 0:
            # Default to hybrid if no keywords
            return TaskClassification(
                task_type=TaskType.HYBRID,
                reasoning_score=0.5,
                coding_score=0.5,
                confidence=0.3,
                keywords_matched=[],
            )
        
        reasoning_score = reasoning_count / total
        coding_score = coding_count / total
        
        # Determine task type
        if reasoning_count > 0 and coding_count > 0:
            task_type = TaskType.HYBRID
        elif reasoning_count > 0:
            task_type = TaskType.REASONING_ONLY
        else:
            task_type = TaskType.CODING_ONLY
        
        # Calculate confidence based on keyword density
        density = total / max(1, len(combined.split()))
        confidence = min(1.0, density * 10)
        
        # Boost confidence if we have JS code
        if js_code and len(js_code) > 100:
            confidence = min(1.0, confidence + 0.2)
        
        return TaskClassification(
            task_type=task_type,
            reasoning_score=reasoning_score,
            coding_score=coding_score,
            confidence=confidence,
            keywords_matched=reasoning_matches + coding_matches,
        )
    
    def route(
        self,
        goal: str,
        description: str = "",
        js_code: str = "",
    ) -> str:
        """
        Route task and return task type string.
        
        Returns:
            "reasoning_only", "coding_only", or "hybrid"
        """
        
        classification = self.classify(goal, description, js_code)
        
        log.info("task_routed",
                task_type=classification.task_type.value,
                confidence=classification.confidence,
                keywords=classification.keywords_matched[:5])
        
        return classification.task_type.value


# =============================================================================
# PROMPT BUILDER
# =============================================================================

class PromptBuilder:
    """Build prompts for different models."""
    
    @staticmethod
    def build_reasoning_prompt(
        js_code: str,
        goal: str = "",
        include_code: bool = True,
    ) -> str:
        """Build prompt for reasoning model (DeepSeek)."""
        
        prompt = f"""You are a professional reverse engineer specializing in JavaScript analysis.

Your task is to analyze the following JavaScript code and identify signature generation logic.

"""
        
        if goal:
            prompt += f"Goal: {goal}\n\n"
        
        prompt += f"JavaScript Code:\n```javascript\n{js_code}\n```\n\n"
        
        prompt += """Please provide a detailed analysis covering:
1. **Signature Generation Logic**: How is the signature computed?
2. **Encryption Algorithms**: What algorithms are used (HMAC, AES, RSA, etc.)?
3. **Key Functions**: Which functions are involved in signature generation?
4. **Data Flow**: How does data flow from input to signature output?
5. **Key Parameters**: Where are the keys and secrets located?
6. **Signable Parameters**: Which URL/body parameters are included in the signature?

Be thorough and precise. Your analysis will be used to generate code."""
        
        return prompt
    
    @staticmethod
    def build_coding_prompt(
        analysis: str,
        goal: str = "",
    ) -> str:
        """Build prompt for coding model (Qwen)."""
        
        prompt = f"""You are a Python code generation expert specializing in reverse engineering.

Based on the following analysis, generate clean, runnable Python code for signature generation.

Analysis:
{analysis}

"""
        
        if goal:
            prompt += f"Goal: {goal}\n\n"
        
        prompt += """Generate complete Python code that:
1. Implements the signature generation logic
2. Uses appropriate libraries (hmac, hashlib, etc.)
3. Includes proper error handling
4. Has clear documentation

Output ONLY the code in a python code block. No explanations needed."""
        
        return prompt
    
    @staticmethod
    def build_hybrid_prompt(
        js_code: str,
        goal: str = "",
    ) -> tuple[str, str]:
        """Build prompts for hybrid task (both models)."""
        
        reasoning_prompt = PromptBuilder.build_reasoning_prompt(js_code, goal)
        
        # For coding, we don't have analysis yet - will be done in two steps
        coding_prompt = f"""Based on the JavaScript code analysis, generate Python signature code.

JavaScript: {js_code[:1000]}...

Goal: {goal}

Generate code now."""
        
        return reasoning_prompt, coding_prompt


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_router() -> TaskRouter:
    """Create task router."""
    return TaskRouter()


def quick_classify(goal: str) -> str:
    """Quick classify task."""
    router = TaskRouter()
    return router.route(goal)