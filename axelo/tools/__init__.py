# Axelo MCP Tools - 自动注册所有 Tools

# Import all tools to trigger registration
from axelo.tools import (
    browser_tool,
    fetch_tool,
    static_tool,
    crypto_tool,
    ai_tool,
    codegen_tool,
    verify_tool,
    flow_tool,
    honeypot_tool,
    web_search_tool,
    deobfuscate_tool,
    trace_tool,
    sigverify_tool,
    captcha_tool,
    signature_extractor_tool,
)

# Also import the base module to ensure registry is initialized
from axelo.tools.base import get_registry, ToolRegistry, BaseTool, ToolSchema

__all__ = [
    "get_registry",
    "ToolRegistry", 
    "BaseTool",
    "ToolSchema",
    "browser_tool",
    "fetch_tool",
    "static_tool",
    "crypto_tool",
    "ai_tool",
    "codegen_tool",
    "verify_tool",
    "flow_tool",
    "honeypot_tool",
    "web_search_tool",
    "deobfuscate_tool",
    "trace_tool",
    "sigverify_tool",
    "captcha_tool",
    "signature_extractor_tool",
]