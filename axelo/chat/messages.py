"""
对话消息格式定义

定义 AI 对话系统中的消息格式
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageType(Enum):
    """消息类型"""
    AI = "ai"           # AI 消息
    USER = "user"       # 用户消息
    SYSTEM = "system"   # 系统消息
    THINKING = "thinking"  # AI 思考中
    PLAN = "plan"       # 执行计划
    TOOL = "tool"       # Tool 执行结果
    ERROR = "error"     # 错误消息
    CONFIRM = "confirm" # 确认请求


class MessageRole(Enum):
    """消息角色"""
    ASSISTANT = "assistant"
    USER = "user"
    SYSTEM = "system"


@dataclass
class Message:
    """对话消息"""
    type: MessageType
    content: str
    role: MessageRole = MessageRole.ASSISTANT
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ai(cls, content: str, **metadata) -> "Message":
        """创建 AI 消息"""
        return cls(type=MessageType.AI, content=content, role=MessageRole.ASSISTANT, metadata=metadata)
    
    @classmethod
    def user(cls, content: str) -> "Message":
        """创建用户消息"""
        return cls(type=MessageType.USER, content=content, role=MessageRole.USER)
    
    @classmethod
    def system(cls, content: str) -> "Message":
        """创建系统消息"""
        return cls(type=MessageType.SYSTEM, content=content, role=MessageRole.SYSTEM)
    
    @classmethod
    def thinking(cls, content: str) -> "Message":
        """创建思考消息"""
        return cls(type=MessageType.THINKING, content=content, role=MessageRole.ASSISTANT, metadata={"streaming": True})
    
    @classmethod
    def plan(cls, content: str, tools: list[str], **metadata) -> "Message":
        """创建计划消息"""
        return cls(type=MessageType.PLAN, content=content, role=MessageRole.ASSISTANT, metadata={"tools": tools, **metadata})
    
    @classmethod
    def confirm(cls, content: str) -> "Message":
        """创建确认请求"""
        return cls(type=MessageType.CONFIRM, content=content, role=MessageRole.ASSISTANT)
    
    @classmethod
    def error(cls, content: str) -> "Message":
        """创建错误消息"""
        return cls(type=MessageType.ERROR, content=content, role=MessageRole.ASSISTANT)


@dataclass
class ConversationContext:
    """对话上下文"""
    url: str | None = None
    goal: str | None = None
    target_info: dict[str, Any] = field(default_factory=dict)
    requires_login: bool = False
    anti_bot_type: str | None = None
    output_format: str = "python"
    crawl_rate: str = "normal"
    budget: str = "medium"
    
    def is_complete(self) -> bool:
        """是否收集完所有必要信息"""
        return bool(self.url and self.goal)
    
    def missing_fields(self) -> list[str]:
        """获取缺失的字段"""
        missing = []
        if not self.url:
            missing.append("url")
        if not self.goal:
            missing.append("goal")
        return missing
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "url": self.url,
            "goal": self.goal,
            "target_info": self.target_info,
            "requires_login": self.requires_login,
            "anti_bot_type": self.anti_bot_type,
            "output_format": self.output_format,
            "crawl_rate": self.crawl_rate,
            "budget": self.budget,
        }


@dataclass
class ExecutionPlan:
    """执行计划"""
    tool_sequence: list[str]
    reasoning: str
    estimated_duration: int = 0  # 秒
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    
    def to_display(self) -> str:
        """转换为可显示的格式"""
        lines = [f"🛠️ 执行计划 (预计 {self.estimated_duration}s):"]
        for i, tool in enumerate(self.tool_sequence, 1):
            lines.append(f"  {i}. {tool}")
        return "\n".join(lines)


@dataclass
class ConversationHistory:
    """对话历史"""
    messages: list[Message] = field(default_factory=list)
    
    def add(self, message: Message) -> None:
        """添加消息"""
        self.messages.append(message)
    
    def get_recent(self, n: int = 10) -> list[Message]:
        """获取最近 n 条消息"""
        return self.messages[-n:]
    
    def to_openai_format(self) -> list[dict[str, Any]]:
        """转换为 OpenAI 格式"""
        return [
            {
                "role": msg.role.value,
                "content": msg.content,
            }
            for msg in self.messages
        ]
    
    def clear(self) -> None:
        """清空历史"""
        self.messages.clear()
