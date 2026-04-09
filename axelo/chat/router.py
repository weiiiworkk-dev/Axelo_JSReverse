"""
AI Conversation Router - AI-driven conversation system
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

import structlog
import httpx

from axelo.chat.messages import (
    ConversationContext,
    ConversationHistory,
    ExecutionPlan,
    Message,
    MessageType,
)
from axelo.chat.ui import get_ui
from axelo.chat.executor import ToolExecutor
from axelo.config import settings

log = structlog.get_logger()


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Axelo, a professional AI reverse engineering assistant that helps users scrape websites.

## Your Role
- You are an efficient assistant - when user says ONE sentence, generate a COMPLETE task plan
- Do not ask questions step by step, infer complete information proactively
- You can call tools to complete tasks

## Core Rule: Generate Complete Plan on First Response

When user states their need, you MUST immediately generate a complete task plan:
1. Target website URL or domain (from user input, do not guess specific brands)
2. Crawling goal (what data user wants)
3. Data quantity (user says X, default 100)
4. Data fields (infer from goal, e.g., "product info" -> "title, price, rating, reviews")
5. Anti-crawling mechanism analysis (infer from website type)
6. Execution plan (tool sequence)

## Output Format Requirements (VERY IMPORTANT)

### DO NOT use Markdown:
- NO *italic*, **bold**
- NO ## headings, ### subheadings
- NO ```code blocks```
- NO - bullet lists
- NO > quotes

### MUST use plain text format:
- Headers use === dividers: ===== Task Plan =====
- Lists use numbers: 1. item  2. item
- Code use [code] wrapper: [code] print('hello') [end]
- Dividers use - or = characters

### Example Plan Output:
```
===== Task Plan =====
Target: example.com
Goal: iPhone 15 product data
Quantity: 100 records
Fields: title, price, rating, reviews, stock status
Anti-crawling: [TBD] - signature verification may be needed

Execution Plan:
  1. browser - visit site, get page structure
  2. fetch - download JS bundles
  3. static - analyze code, extract signatures
  4. crypto - analyze encryption
  5. codegen - generate crawler code
  6. verify - verify code works

===== Confirmation =====
Confirm this plan? Enter "confirm" to execute, or "cancel" to restart.
```

## Inference Rules

- Infer goals and fields from user intent.
- Do not use any site-specific mapping table.
- If user input is incomplete, infer and mark [TBD].

## Available Tools
1. web_search - Web search (confirm website info)
2. fetch - Download web pages, JS bundles
3. browser - Browser automation, get cookies, execute JS
4. static - Extract signature candidates from JS
5. crypto - Detect AES/RSA/HMAC/SHA encryption
6. ai_analyze - Generate signature hypotheses
7. codegen - Generate crawler code
8. verify - Test if code works

## Style
- Give the plan directly, don't ask too many questions
- Use plain text structured output
- Concise but complete"""


# ============================================================================
# Text Processor
# ============================================================================

class TextProcessor:
    """Clean AI output - remove Markdown formatting"""
    
    @staticmethod
    def clean(text: str) -> str:
        """Remove Markdown formatting"""
        import re
        
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', lambda m: TextProcessor._format_code(m.group(0)), text)
        
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'[code] \1 [end]', text)
        
        # Remove bold
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        
        # Remove italic
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        
        # Remove headings
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        
        # Remove quotes
        text = re.sub(r'^>\s*', '| ', text, flags=re.MULTILINE)
        
        # Clean lists
        text = re.sub(r'^-\s+', '  - ', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+', lambda m: f'  {m.group(0).rstrip(". ")}. ', text, flags=re.MULTILINE)
        
        # Clean extra blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    @staticmethod
    def _format_code(block: str) -> str:
        """Convert code block to plain text"""
        import re
        match = re.match(r'```(\w*)\n?([\s\S]*?)```', block)
        if match:
            lang = match.group(1) or 'code'
            code = match.group(2).strip()
            return f'\n[code - {lang}]\n{code}\n{"=" * 40}\n'
        return block


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ConversationState:
    """Conversation state"""
    waiting_for_url: bool = True
    waiting_for_goal: bool = False
    has_url: bool = False
    has_goal: bool = False
    url: str = ""
    goal: str = ""
    pending_tool_call: bool = False
    last_ai_error: str = ""
    plan_ready: bool = False
    executing: bool = False
    planned_tools: list[str] | None = None


@dataclass
class ToolCall:
    """Tool call request"""
    tool_name: str
    arguments: dict[str, Any]


# ============================================================================
# Conversation Router
# ============================================================================

class ConversationRouter:
    """AI-driven conversation router with Tool Calling support"""
    
    def __init__(self):
        self.ui = get_ui()
        self.context = ConversationContext()
        self.history = ConversationHistory()
        self._tools: dict[str, Any] = {}
        self._on_thinking: Callable | None = None
        self._executor = ToolExecutor()
        self._conv_state = ConversationState()
        self._system_prompt = SYSTEM_PROMPT
        self._ai_client = None
        self._max_tool_calls = 3
    
    def register_tool(self, name: str, tool: Any) -> None:
        """Register a tool"""
        self._tools[name] = tool
    
    def set_thinking_callback(self, callback: Callable) -> None:
        """Set thinking callback"""
        self._on_thinking = callback
    
    def _get_tool_schemas(self) -> list[dict]:
        """Get tool schemas for Tool Calling"""
        schemas = []
        
        tools = {
            "web_search": {
                "description": "Web search for website info",
                "params": {
                    "query": {"type": "string", "description": "search query"},
                },
            },
            "fetch": {
                "description": "Download JS bundles and HTML",
                "params": {
                    "url": {"type": "string", "description": "target URL"},
                    "type": {
                        "type": "string",
                        "description": "content type",
                        "enum": ["html", "js", "json"],
                    },
                },
            },
            "browser": {
                "description": "Browser automation",
                "params": {
                    "url": {"type": "string", "description": "target URL"},
                    "goal": {"type": "string", "description": "crawl goal"},
                },
            },
            "static": {
                "description": "Static analysis of JS code",
                "params": {
                    "js_code": {"type": "string", "description": "JavaScript code"},
                },
            },
            "crypto": {
                "description": "Crypto analysis",
                "params": {
                    "js_code": {"type": "string", "description": "JavaScript code"},
                },
            },
            "ai_analyze": {
                "description": "AI analysis",
                "params": {
                    "goal": {"type": "string", "description": "analysis goal"},
                    "candidates": {"type": "array", "description": "signature candidates"},
                },
            },
            "codegen": {
                "description": "Code generation",
                "params": {
                    "hypothesis": {"type": "string", "description": "signature hypothesis"},
                    "target_url": {"type": "string", "description": "target URL"},
                },
            },
            "verify": {
                "description": "Verify code works",
                "params": {
                    "code": {"type": "string", "description": "code to verify"},
                    "target_url": {"type": "string", "description": "test URL"},
                },
            }
        }
        
        for name, info in tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": info["description"],
                    "parameters": {
                        "type": "object",
                        "properties": info["params"],
                        "required": list(info["params"].keys())[:1],
                    }
                }
            })
        
        return schemas
    
    @property
    def _conversation_history_text(self) -> str:
        lines = []
        for msg in self.history.messages:
            if msg.type == MessageType.USER:
                lines.append(f"User: {msg.content}")
            elif msg.type == MessageType.AI:
                lines.append(f"AI: {msg.content}")
        return "\n".join(lines[-10:])
    
    async def _call_ai(self, user_input: str, tool_call_mode: bool = False) -> tuple[str, list[dict]]:
        messages = [{"role": "system", "content": self._system_prompt}]
        
        state_info = []
        if self._conv_state.has_url:
            state_info.append(f"Target: {self._conv_state.url}")
        if self._conv_state.has_goal:
            state_info.append(f"Goal: {self._conv_state.goal}")
        
        if state_info:
            messages.append({"role": "system", "content": f"State:\n" + "\n".join(state_info)})
        
        history_text = self._conversation_history_text
        if history_text:
            messages.append({"role": "system", "content": f"History:\n{history_text}"})
        
        messages.append({"role": "user", "content": user_input})
        
        deepseek_api_key = (getattr(settings, "deepseek_api_key", None) or "").strip()

        if not deepseek_api_key:
            self._conv_state.last_ai_error = "No AI API key configured"
            return self._fallback_response(user_input), []
        
        try:
            content, tool_calls = await self._call_deepseek(messages, deepseek_api_key, tool_call_mode)
            self._conv_state.last_ai_error = ""
            return content, tool_calls
        except Exception as e:
            self._conv_state.last_ai_error = str(e)
            log.warning("ai_call_failed", error=str(e), provider="deepseek")
            return self._fallback_response(user_input), []

    async def _call_deepseek(
        self,
        messages: list[dict[str, str]],
        api_key: str,
        tool_call_mode: bool,
    ) -> tuple[str, list[dict]]:
        payload: dict[str, Any] = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        if not tool_call_mode:
            payload["tools"] = self._get_tool_schemas()

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            message = result["choices"][0]["message"]
            return message.get("content", ""), message.get("tool_calls", [])

    def _parse_tool_calls(self, tool_calls: list[dict]) -> list[ToolCall]:
        parsed = []
        for tc in tool_calls:
            if "function" in tc:
                func = tc["function"]
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {"raw": func.get("arguments", "")}
                parsed.append(ToolCall(tool_name=func.get("name", ""), arguments=args))
        return parsed
    
    async def _execute_tool_call(self, tool_call: ToolCall) -> str:
        tool_name = tool_call.tool_name
        args = tool_call.arguments
        
        log.info("executing_tool_call", tool=tool_name, args=args)
        
        try:
            result = await self._executor.execute_tool(tool_name, args)
            
            if result.success:
                output = result.output
                if tool_name == "web_search":
                    results = output.get("results", [])
                    if results:
                        formatted = "Search results:\n"
                        for i, r in enumerate(results[:3], 1):
                            formatted += f"{i}. {r.get('title', '')}\n"
                            formatted += f"   URL: {r.get('url', '')}\n"
                        return formatted
                    return "No results found"
                return json.dumps(output, ensure_ascii=False, indent=2)
            return f"Tool failed: {result.error}"
        except Exception as e:
            return f"Tool error: {str(e)}"
    
    def _fallback_response(self, user_input: str) -> str:
        if self._conv_state.last_ai_error:
            return (
                f"AI call failed: {self._conv_state.last_ai_error}\n"
                "Please check API key/provider settings, then continue by providing target URL."
            )
        if self._conv_state.waiting_for_url:
            return "Please tell me the target website URL (e.g., example.com)"
        if self._conv_state.waiting_for_goal:
            return "What's your crawling goal? (e.g., product list, user reviews)"
        if self._conv_state.has_url and self._conv_state.has_goal:
            return "Got all info. Enter 'confirm' to execute, or 'cancel' to restart."
        return "Hello! Tell me what website you want to crawl."
    
    async def process_input(self, user_input: str) -> Message:
        text = user_input.lower().strip()
        
        confirm_keywords = ["confirm", "yes", "y", "ok", "execute", "start"]
        cancel_keywords = ["cancel", "stop", "quit", "restart"]
        
        text_words = text.split()
        for kw in cancel_keywords:
            if kw in text_words or text.startswith(kw):
                self._conv_state = ConversationState()
                return Message.ai("Restarted. What website do you want to crawl?")
        
        self._update_conversation_state(user_input)
        if self._is_confirmation_text(text, confirm_keywords):
            # Accept confirm only when required inputs are complete.
            if self._conv_state.has_url and self._conv_state.url and self._conv_state.has_goal:
                return await self._handle_confirm(user_input)
            missing = []
            if not (self._conv_state.has_url and self._conv_state.url):
                missing.append("target URL")
            if not self._conv_state.has_goal:
                missing.append("goal")
            return Message.ai(
                f"Cannot execute yet. Missing required input: {', '.join(missing)}. "
                "Please provide the missing information, then confirm again."
            )
        
        user_msg = Message.user(user_input)
        self.history.add(user_msg)
        
        ai_response, tool_calls = await self._call_ai(user_input)
        
        tool_call_count = 0
        while tool_calls and tool_call_count < self._max_tool_calls:
            if self._on_thinking:
                self._on_thinking(f"Calling: {', '.join(tc['function']['name'] for tc in tool_calls)}")
            
            for tc in tool_calls:
                parsed = self._parse_tool_calls([tc])
                for pc in parsed:
                    result = await self._execute_tool_call(pc)
                    self.history.add(Message.system(f"[{pc.tool_name}] Result:\n{result}"))
                    if self._should_stop_tool_loop(pc.tool_name, result):
                        ai_response = "Tool execution reached completion criteria."
                        tool_calls = []
                        break
                if not tool_calls:
                    break
            
            if tool_calls:
                ai_response, tool_calls = await self._call_ai("Continue based on tool results", tool_call_mode=True)
                tool_call_count += 1
        
        ai_response = TextProcessor.clean(ai_response)
        self._sync_state_from_plan_text(ai_response)
        ai_msg = Message.ai(ai_response)
        return ai_msg

    def _should_stop_tool_loop(self, tool_name: str, result_text: str) -> bool:
        if tool_name == "verify":
            return True
        if tool_name == "codegen":
            lowered = (result_text or "").lower()
            if "tool failed" in lowered or "tool error" in lowered:
                return True
        return False

    def _sync_state_from_plan_text(self, ai_text: str) -> None:
        text = ai_text or ""
        lowered = text.lower()
        looks_like_plan = ("execution plan" in lowered and "confirm" in lowered) or ("===== task plan =====" in lowered)
        self._conv_state.plan_ready = looks_like_plan
        if not looks_like_plan:
            self._conv_state.planned_tools = None
            return

        target_match = re.search(r"(?im)^target:\s*(.+)\s*$", text)
        if target_match:
            target_raw = target_match.group(1).strip()
            if target_raw and "[tbd]" not in target_raw.lower():
                domain_match = re.search(r"([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", target_raw)
                if domain_match:
                    url = domain_match.group(1)
                    if not url.startswith("http"):
                        url = f"https://{url}"
                    self._conv_state.url = url
                    self._conv_state.has_url = True
                    self._conv_state.waiting_for_url = False

        goal_match = re.search(r"(?im)^goal:\s*(.+)\s*$", text)
        if goal_match:
            goal_raw = goal_match.group(1).strip()
            if goal_raw and "[tbd]" not in goal_raw.lower():
                self._conv_state.goal = goal_raw
                self._conv_state.has_goal = True
                self._conv_state.waiting_for_goal = False

        # Parse execution plan tool sequence from AI text, if present.
        self._conv_state.planned_tools = self._extract_plan_tools(text)

    def _extract_plan_tools(self, text: str) -> list[str]:
        tools: list[str] = []
        for line in (text or "").splitlines():
            line_norm = line.strip().lower()
            match = re.match(r"^\d+\.\s*([a-z_]+)\b", line_norm)
            if not match:
                continue
            tool_name = match.group(1)
            if tool_name in {
                "web_search",
                "fetch",
                "fetch_js_bundles",
                "browser",
                "static",
                "crypto",
                "ai_analyze",
                "codegen",
                "verify",
            }:
                tools.append(tool_name)
        return tools

    def _is_confirmation_text(self, text: str, confirm_keywords: list[str]) -> bool:
        normalized = text.strip().lower()
        if not normalized:
            return False
        # Require exact match for short keywords like "y"/"ok" to avoid accidental triggers.
        if normalized in confirm_keywords:
            return True
        # Allow explicit command prefix for natural inputs like "confirm now".
        return any(normalized.startswith(f"{kw} ") for kw in ("confirm", "execute", "start"))
    
    def _update_conversation_state(self, user_input: str) -> None:
        text = user_input.lower().strip()
        
        if "http" in user_input or user_input.startswith("www.") or self._looks_like_url(user_input):
            url_match = re.search(r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', user_input)
            if url_match:
                url = url_match.group(0)
                if not url.startswith("http"):
                    url = f"https://{url}"
                self._conv_state.url = url
                self._conv_state.has_url = True
                self._conv_state.waiting_for_url = False
        
        goal_keywords = ["crawl", "get", "fetch", "scrape", "product", "review", "data", "iphone", "phone", "search"]
        if any(kw in text for kw in goal_keywords):
            if self._conv_state.has_url:
                self._conv_state.goal = user_input
                self._conv_state.has_goal = True
                self._conv_state.waiting_for_goal = False
            elif not self._conv_state.has_goal:
                self._conv_state.goal = user_input
                self._conv_state.has_goal = True
                self._conv_state.waiting_for_goal = False
                self._conv_state.waiting_for_url = True
    
    def _looks_like_url(self, text: str) -> bool:
        return bool(re.match(r'^[\w.-]+\.[\w.-]+', text))
    
    async def _generate_plan(self) -> Message:
        thinking = self._generate_thinking()
        if self._on_thinking:
            self._on_thinking(thinking)
        
        tools = self._select_tools()
        
        reasoning = f"Based on '{self._conv_state.goal}', execution plan:\n"
        for i, tool in enumerate(tools, 1):
            reasoning += f"  {i}. {tool}\n"
        
        plan = ExecutionPlan(tool_sequence=tools, reasoning=reasoning, estimated_duration=120)
        self.context.target_info = {"plan": plan}
        
        return Message.plan(content=reasoning, tools=plan.tool_sequence)
    
    def _generate_thinking(self) -> str:
        lines = ["Analyzing target...", "", f"Target: {self._conv_state.url}", f"Goal: {self._conv_state.goal}"]
        tools = self._select_tools()
        lines.append(f"Tools: {', '.join(tools)}")
        return "\n".join(lines)
    
    def _select_tools(self) -> list[str]:
        goal = self._conv_state.goal.lower()
        tools = ["browser"]
        if "js" in goal or "javascript" in goal or "analyze" in goal:
            tools.extend(["fetch_js_bundles", "static"])
            if "crypto" in goal or "encrypt" in goal:
                tools.append("crypto")
        tools.extend(["ai_analyze", "codegen", "verify"])
        return tools
    
    async def execute_plan(self) -> dict[str, Any]:
        tools = self._conv_state.planned_tools or self._select_tools()
        initial_input = {"url": self._conv_state.url, "goal": self._conv_state.goal}
        results = await self._executor.execute_sequence(tools, initial_input)
        outputs = self._executor.get_outputs()
        return {"tools": tools, "results": {k: {"success": v.success, "error": v.error} for k, v in results.items()}, "outputs": outputs}
    
    async def _handle_confirm(self, text: str) -> Message:
        self._conv_state.executing = True
        self._conv_state.plan_ready = False
        try:
            result = await self.execute_plan()
            outputs = result.get("outputs", {})
            if "python_code" in outputs:
                code = outputs["python_code"]
                return Message(type=MessageType.AI, content=f"Done! Code:\n\n{code[:1000]}...")
            if "codegen" in result.get("results", {}):
                codegen_result = result["results"].get("codegen", {})
                if not codegen_result.get("success"):
                    return Message.error(f"Failed: {codegen_result.get('error', 'Unknown')}")
            if "verify" in result.get("results", {}):
                verify_result = result["results"].get("verify", {})
                if verify_result.get("success"):
                    return Message.ai("Execution completed: codegen + verify passed.")
                return Message.error(f"Verify failed: {verify_result.get('error', 'Unknown')}")
            return Message.ai(f"Executed {len(result['tools'])} tools")
        finally:
            self._conv_state.executing = False
    
    def get_context(self) -> ConversationContext:
        return self.context
    
    def reset(self) -> None:
        self.context = ConversationContext()
        self.history.clear()
        self._conv_state = ConversationState()
