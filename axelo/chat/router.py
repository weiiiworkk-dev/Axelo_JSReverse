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


def _is_placeholder_value(value: str) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return True
    placeholder_markers = [
        "[tbd]",
        "tbd",
        "待确认",
        "需要确认",
        "用户未提供",
        "未提供具体网站",
        "请提供",
        "to be determined",
    ]
    return any(marker in text for marker in placeholder_markers)


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """你是 Axelo，一个专业的 AI 逆向工程助手，帮助用户抓取网站数据。

## 你的角色
- 你是高效助手：当用户只说一句话，也要直接生成完整任务计划
- 不要逐步追问，优先主动推断完整信息
- 你可以调用工具完成任务

## 核心规则：首轮必须给出完整计划

当用户表达需求时，你必须立即输出完整任务计划，包含：
1. 目标网站 URL 或域名（从用户输入提取，不要猜测具体品牌）
2. 抓取目标（用户要什么数据）
3. 数据量（用户未指定时默认 100）
4. 字段清单（根据目标推断，例如“商品信息”->“标题、价格、评分、评论数”）
5. 反爬机制分析（根据网站类型推断）
6. 执行计划（工具调用顺序）

## 输出格式要求（非常重要）

### 禁止使用 Markdown：
- 不要使用 *斜体*、**加粗**
- 不要使用 ## 标题、### 子标题
- 不要使用 ```代码块```
- 不要使用 - 无序列表
- 不要使用 > 引用

### 必须使用纯文本格式：
- 标题使用等号分隔：===== 任务计划 =====
- 列表使用数字：1. 项目  2. 项目
- 代码使用 [code] 包裹：[code] print('hello') [end]
- 分隔线使用 - 或 = 字符

### 计划输出示例：
=====
任务计划
=====
目标: example.com
目标数据: iPhone 15 商品数据
数量: 100 条
字段: 标题, 价格, 评分, 评论数, 库存状态
反爬分析: [TBD] - 可能需要签名校验

执行计划:
  1. browser - 访问站点并获取页面结构
  2. fetch - 下载 JS 资源与页面内容
  3. static - 分析代码并提取签名候选
  4. crypto - 识别加密与摘要算法
  5. codegen - 生成抓取代码
  6. verify - 验证代码可用性

=====
确认
=====
请确认此计划。输入“确认”开始执行，输入“取消”重新开始。

## 推断规则

- 根据用户意图推断抓取目标与字段
- 不要依赖站点专用映射表
- 输入不完整时可推断，并用 [TBD] 标记

## 可用工具
1. web_search - 联网搜索（确认站点信息）
2. fetch - 下载网页与 JS 资源
3. browser - 浏览器自动化（获取 Cookie、执行 JS）
4. static - 对 JS 做静态分析，提取签名候选
5. crypto - 识别 AES/RSA/HMAC/SHA 等加密特征
6. ai_analyze - 生成签名假设
7. codegen - 生成抓取代码
8. verify - 验证代码是否有效

## 风格
- 直接给出计划，不要过度提问
- 使用结构化纯文本输出
- 简洁但完整"""


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
                lines.append(f"用户: {msg.content}")
            elif msg.type == MessageType.AI:
                lines.append(f"助手: {msg.content}")
        return "\n".join(lines[-10:])
    
    async def _call_ai(self, user_input: str, tool_call_mode: bool = False) -> tuple[str, list[dict]]:
        messages = [{"role": "system", "content": self._system_prompt}]
        
        state_info = []
        if self._conv_state.has_url:
            state_info.append(f"目标网址: {self._conv_state.url}")
        if self._conv_state.has_goal:
            state_info.append(f"抓取目标: {self._conv_state.goal}")
        
        if state_info:
            messages.append({"role": "system", "content": f"状态:\n" + "\n".join(state_info)})
        
        history_text = self._conversation_history_text
        if history_text:
            messages.append({"role": "system", "content": f"对话历史:\n{history_text}"})
        
        messages.append({"role": "user", "content": user_input})
        
        deepseek_api_key = (getattr(settings, "deepseek_api_key", None) or "").strip()

        if not deepseek_api_key:
            self._conv_state.last_ai_error = "未配置 AI API Key"
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
                f"AI 调用失败: {self._conv_state.last_ai_error}\n"
                "请检查 API Key 或模型提供方配置，然后继续提供目标网址。"
            )
        if self._conv_state.waiting_for_url:
            return "请提供目标网站网址（例如：example.com）"
        if self._conv_state.waiting_for_goal:
            return "请说明你的抓取目标（例如：商品列表、用户评论）"
        if self._conv_state.has_url and self._conv_state.has_goal:
            return "信息已齐全。输入“确认”开始执行，或输入“取消”重新开始。"
        return "你好！请告诉我你想抓取哪个网站。"
    
    async def process_input(self, user_input: str) -> Message:
        text = user_input.lower().strip()
        
        confirm_keywords = ["确认", "执行", "开始", "继续"]
        cancel_keywords = ["取消", "停止", "退出", "重来", "重新开始"]
        
        text_words = text.split()
        for kw in cancel_keywords:
            if kw in text_words or text.startswith(kw):
                self._conv_state = ConversationState()
                return Message.ai("已重置。请告诉我你要抓取的网站网址。")
        
        self._update_conversation_state(user_input)
        is_confirm = self._is_confirmation_text(text, confirm_keywords)
        if is_confirm:
            # 仅在必要输入齐全时接受确认执行。
            can_execute_with_search = (
                self._conv_state.has_goal
                and self._conv_state.plan_ready
                and bool(self._conv_state.planned_tools)
                and ("web_search" in (self._conv_state.planned_tools or []))
            )
            if (self._conv_state.has_url and self._conv_state.url and self._conv_state.has_goal) or can_execute_with_search:
                return await self._handle_confirm(user_input)
            missing = []
            if not (self._conv_state.has_url and self._conv_state.url):
                missing.append("目标网址")
            if not self._conv_state.has_goal:
                missing.append("抓取目标")
            return Message.ai(
                f"暂时无法执行。缺少必要信息：{', '.join(missing)}。"
                "请先补充缺失信息，再输入“确认”。"
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
                ai_response, tool_calls = await self._call_ai("请基于工具结果继续", tool_call_mode=True)
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
        looks_like_plan = (
            ("执行计划" in text and "确认" in text)
            or ("===== 任务计划 =====" in text)
            or ("execution plan" in lowered and "confirm" in lowered)
        )
        self._conv_state.plan_ready = looks_like_plan
        if not looks_like_plan:
            self._conv_state.planned_tools = None
            return

        target_match = (
            re.search(r"(?im)^目标(?:网址)?\s*:\s*(.+)\s*$", text)
            or re.search(r"(?im)^target:\s*(.+)\s*$", text)
        )
        if target_match:
            target_raw = target_match.group(1).strip()
            if target_raw and not _is_placeholder_value(target_raw):
                domain_match = re.search(r"([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", target_raw)
                if domain_match:
                    url = domain_match.group(1)
                    if not url.startswith("http"):
                        url = f"https://{url}"
                    self._conv_state.url = url
                    self._conv_state.has_url = True
                    self._conv_state.waiting_for_url = False

        goal_match = (
            re.search(r"(?im)^目标(?:数据|内容|任务)?\s*:\s*(.+)\s*$", text)
            or re.search(r"(?im)^抓取目标\s*:\s*(.+)\s*$", text)
            or re.search(r"(?im)^goal:\s*(.+)\s*$", text)
        )
        if goal_match:
            goal_raw = goal_match.group(1).strip()
            if goal_raw and not _is_placeholder_value(goal_raw):
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
        # Some Windows terminal/codepage paths can turn "确认" into "??".
        if normalized in {"??", "？？"}:
            return True
        # 中文确认关键词使用精确匹配，避免误触发。
        if normalized in confirm_keywords:
            return True
        # 允许自然命令前缀，如“确认执行”“开始执行”
        return any(normalized.startswith(kw) for kw in ("确认", "执行", "开始", "继续"))
    
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
        
        goal_keywords = [
            "抓取",
            "采集",
            "爬取",
            "获取",
            "搜索",
            "商品",
            "评论",
            "数据",
            "价格",
            "销量",
            "店铺",
            "关键词",
            "手机",
            "苹果",
            "请求",
            "接口",
        ]
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
        # Fallback for mojibake/input degradation where Chinese becomes "??".
        # Keep it conservative: only infer goal when meaningful ASCII/digits exist.
        elif (
            not self._conv_state.has_goal
            and text
            and re.search(r"[a-z0-9]", text)
            and len(text) >= 3
        ):
            self._conv_state.goal = user_input
            self._conv_state.has_goal = True
            self._conv_state.waiting_for_goal = False
            if not self._conv_state.has_url:
                self._conv_state.waiting_for_url = True
    
    def _looks_like_url(self, text: str) -> bool:
        return bool(re.match(r'^[\w.-]+\.[\w.-]+', text))
    
    async def _generate_plan(self) -> Message:
        thinking = self._generate_thinking()
        if self._on_thinking:
            self._on_thinking(thinking)
        
        tools = self._select_tools()
        
        reasoning = f"基于“{self._conv_state.goal}”，执行计划如下：\n"
        for i, tool in enumerate(tools, 1):
            reasoning += f"  {i}. {tool}\n"
        
        plan = ExecutionPlan(tool_sequence=tools, reasoning=reasoning, estimated_duration=120)
        self.context.target_info = {"plan": plan}
        
        return Message.plan(content=reasoning, tools=plan.tool_sequence)
    
    def _generate_thinking(self) -> str:
        lines = ["正在分析目标...", "", f"目标网址: {self._conv_state.url}", f"抓取目标: {self._conv_state.goal}"]
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
        tools = self._normalize_tool_sequence(tools)
        initial_input = {"url": self._conv_state.url, "goal": self._conv_state.goal}
        results = await self._executor.execute_sequence(tools, initial_input)
        outputs = self._executor.get_outputs()
        return {"tools": tools, "results": {k: {"success": v.success, "error": v.error} for k, v in results.items()}, "outputs": outputs}

    def _normalize_tool_sequence(self, tools: list[str]) -> list[str]:
        """
        Ensure static/crypto analysis has JS bundle inputs.

        Some AI plans include `fetch` before `static`, which only provides page
        content and can leave `static` without usable JS code. We normalize the
        sequence by inserting `fetch_js_bundles` before the first analysis step
        that requires JS code.
        """
        seq = list(tools or [])
        if not seq:
            return seq
        needs_js = any(name in {"static", "crypto", "flow"} for name in seq)
        if not needs_js:
            return seq
        if "fetch_js_bundles" in seq:
            return seq

        insert_at = len(seq)
        for i, name in enumerate(seq):
            if name in {"static", "crypto", "flow"}:
                insert_at = i
                break
        seq.insert(insert_at, "fetch_js_bundles")
        return seq
    
    async def _handle_confirm(self, text: str) -> Message:
        self._conv_state.executing = True
        self._conv_state.plan_ready = False
        try:
            result = await self.execute_plan()
            outputs = result.get("outputs", {})
            if "python_code" in outputs:
                code = outputs["python_code"]
                return Message(type=MessageType.AI, content=f"执行完成！代码如下：\n\n{code[:1000]}...")
            if "codegen" in result.get("results", {}):
                codegen_result = result["results"].get("codegen", {})
                if not codegen_result.get("success"):
                    return Message.error(f"执行失败：{codegen_result.get('error', '未知错误')}")
            if "verify" in result.get("results", {}):
                verify_result = result["results"].get("verify", {})
                if verify_result.get("success"):
                    return Message.ai("执行完成：codegen 与 verify 均通过。")
                return Message.error(f"验证失败：{verify_result.get('error', '未知错误')}")
            return Message.ai(f"已执行 {len(result['tools'])} 个工具")
        finally:
            self._conv_state.executing = False
    
    def get_context(self) -> ConversationContext:
        return self.context
    
    def reset(self) -> None:
        self.context = ConversationContext()
        self.history.clear()
        self._conv_state = ConversationState()
