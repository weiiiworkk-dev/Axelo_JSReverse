"""
Error Handling System for Axelo Tools

Provides:
- Error classification (retryable vs fatal)
- Error codes for tool failures
- Consistent error logging
"""
from __future__ import annotations

from enum import Enum
from typing import Any
import structlog

log = structlog.get_logger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"         # Can continue, warn user
    MEDIUM = "medium"   # Need retry or fallback
    HIGH = "high"       # Tool failed, need alternative
    CRITICAL = "critical"  # System error, stop execution


class ErrorCategory(Enum):
    """Error categories for classification"""
    # Network related
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_CONNECTION = "network_connection"
    NETWORK_DNS = "network_dns"
    
    # Authentication/Authorization
    AUTH_REQUIRED = "auth_required"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    
    # Data processing
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    DATA_MISSING = "data_missing"
    
    # Execution
    EXECUTION_TIMEOUT = "execution_timeout"
    EXECUTION_FAILED = "execution_failed"
    DEPENDENCY_MISSING = "dependency_missing"
    
    # Anti-bot/Detection
    ANTIBOT_DETECTED = "antibot_detected"
    CAPTCHA_REQUIRED = "captcha_required"
    
    # System
    SYSTEM_ERROR = "system_error"
    NOT_IMPLEMENTED = "not_implemented"
    UNKNOWN = "unknown"


# Error classification mapping
ERROR_PATTERNS: dict[str, tuple[ErrorCategory, ErrorSeverity]] = {
    # Network errors
    "timeout": (ErrorCategory.NETWORK_TIMEOUT, ErrorSeverity.MEDIUM),
    "Timed out": (ErrorCategory.NETWORK_TIMEOUT, ErrorSeverity.MEDIUM),
    "Connection refused": (ErrorCategory.NETWORK_CONNECTION, ErrorSeverity.MEDIUM),
    "Connection reset": (ErrorCategory.NETWORK_CONNECTION, ErrorSeverity.MEDIUM),
    "DNS lookup failed": (ErrorCategory.NETWORK_DNS, ErrorSeverity.HIGH),
    "Name or service not known": (ErrorCategory.NETWORK_DNS, ErrorSeverity.HIGH),
    
    # Auth errors
    "401": (ErrorCategory.AUTH_FAILED, ErrorSeverity.HIGH),
    "403": (ErrorCategory.AUTH_FAILED, ErrorSeverity.HIGH),
    "unauthorized": (ErrorCategory.AUTH_FAILED, ErrorSeverity.HIGH),
    "Forbidden": (ErrorCategory.AUTH_FAILED, ErrorSeverity.HIGH),
    "429": (ErrorCategory.RATE_LIMITED, ErrorSeverity.MEDIUM),
    "Too Many Requests": (ErrorCategory.RATE_LIMITED, ErrorSeverity.MEDIUM),
    
    # Data errors
    "JSONDecodeError": (ErrorCategory.PARSE_ERROR, ErrorSeverity.MEDIUM),
    "cannot parse": (ErrorCategory.PARSE_ERROR, ErrorSeverity.MEDIUM),
    "missing required": (ErrorCategory.VALIDATION_ERROR, ErrorSeverity.MEDIUM),
    "not found": (ErrorCategory.DATA_MISSING, ErrorSeverity.MEDIUM),
    "empty response": (ErrorCategory.DATA_MISSING, ErrorSeverity.LOW),
    
    # Execution errors
    "SyntaxError": (ErrorCategory.EXECUTION_FAILED, ErrorSeverity.HIGH),
    "ImportError": (ErrorCategory.DEPENDENCY_MISSING, ErrorSeverity.HIGH),
    "ModuleNotFoundError": (ErrorCategory.DEPENDENCY_MISSING, ErrorSeverity.HIGH),
    "AttributeError": (ErrorCategory.EXECUTION_FAILED, ErrorSeverity.HIGH),
    "executing failed": (ErrorCategory.EXECUTION_FAILED, ErrorSeverity.HIGH),
    
    # Anti-bot
    "captcha": (ErrorCategory.ANTIBOT_DETECTED, ErrorSeverity.HIGH),
    "CAPTCHA": (ErrorCategory.ANTIBOT_DETECTED, ErrorSeverity.HIGH),
    "验证码": (ErrorCategory.ANTIBOT_DETECTED, ErrorSeverity.HIGH),
    "blocked": (ErrorCategory.ANTIBOT_DETECTED, ErrorSeverity.HIGH),
    "Cloudflare": (ErrorCategory.ANTIBOT_DETECTED, ErrorSeverity.HIGH),
    "Turnstile": (ErrorCategory.CAPTCHA_REQUIRED, ErrorSeverity.HIGH),
    
    # System
    "NotImplementedError": (ErrorCategory.NOT_IMPLEMENTED, ErrorSeverity.MEDIUM),
    "NotImplementedError": (ErrorCategory.NOT_IMPLEMENTED, ErrorSeverity.MEDIUM),
    "RuntimeError": (ErrorCategory.SYSTEM_ERROR, ErrorSeverity.CRITICAL),
}


def classify_error(error: Exception | str) -> tuple[ErrorCategory, ErrorSeverity]:
    """
    Classify an error based on its message or string representation
    
    Returns:
        (category, severity)
    """
    error_str = str(error).lower()
    
    for pattern, (category, severity) in ERROR_PATTERNS.items():
        if pattern.lower() in error_str:
            return category, severity
    
    # Default: unknown error, medium severity
    return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM


def is_retryable_error(error: Exception | str) -> bool:
    """
    Determine if an error is retryable
    
    Returns True for network timeouts, rate limits, temporary failures
    """
    _, severity = classify_error(error)
    return severity in (ErrorSeverity.LOW, ErrorSeverity.MEDIUM)


def get_error_recovery_action(category: ErrorCategory, severity: ErrorSeverity) -> str:
    """
    Get recommended recovery action based on error classification
    """
    if category == ErrorCategory.NETWORK_TIMEOUT:
        return "retry_with_backoff"
    elif category == ErrorCategory.NETWORK_CONNECTION:
        return "retry_with_backoff"
    elif category == ErrorCategory.RATE_LIMITED:
        return "wait_and_retry"
    elif category == ErrorCategory.AUTH_FAILED:
        return "use_alternative_auth"
    elif category == ErrorCategory.ANTIBOT_DETECTED:
        return "change_fingerprint"
    elif category == ErrorCategory.CAPTCHA_REQUIRED:
        return "manual_intervention"
    elif category == ErrorCategory.DEPENDENCY_MISSING:
        return "install_dependency"
    elif category == ErrorCategory.NOT_IMPLEMENTED:
        return "skip_or_fallback"
    elif severity == ErrorSeverity.CRITICAL:
        return "stop_execution"
    else:
        return "continue_with_warning"


def log_tool_error(
    tool_name: str,
    error: Exception | str,
    context: dict[str, Any] = None
) -> None:
    """
    Log tool error with classification
    """
    category, severity = classify_error(error)
    recovery = get_error_recovery_action(category, severity)
    
    log_dict = {
        "tool": tool_name,
        "error": str(error),
        "category": category.value,
        "severity": severity.value,
        "recovery_action": recovery,
    }
    
    if context:
        log_dict["context"] = context
    
    # Log at appropriate level
    if severity == ErrorSeverity.CRITICAL:
        log.error("tool_error_critical", **log_dict)
    elif severity == ErrorSeverity.HIGH:
        log.error("tool_error_high", **log_dict)
    elif severity == ErrorSeverity.MEDIUM:
        log.warning("tool_error_medium", **log_dict)
    else:
        log.info("tool_error_low", **log_dict)


# Decorator for tool error handling
from functools import wraps
from typing import Callable
import asyncio


def handle_tool_errors(func: Callable) -> Callable:
    """
    Decorator to handle tool errors with classification
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            from axelo.tools.base import ToolResult, ToolStatus
            
            # Classify and log the error
            tool_name = kwargs.get('tool_name', 'unknown')
            log_tool_error(tool_name, e, {"args": str(args)[:200]})
            
            # Determine if retryable
            if is_retryable_error(e):
                # Let the base tool's retry logic handle it
                raise
            
            # Return a failed result for non-retryable errors
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.FAILED,
                error=str(e)
            )
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            from axelo.tools.base import ToolResult, ToolStatus
            
            tool_name = kwargs.get('tool_name', 'unknown')
            log_tool_error(tool_name, e, {"args": str(args)[:200]})
            
            if is_retryable_error(e):
                raise
            
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.FAILED,
                error=str(e)
            )
    
    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


__all__ = [
    "ErrorSeverity",
    "ErrorCategory", 
    "classify_error",
    "is_retryable_error",
    "get_error_recovery_action",
    "log_tool_error",
    "handle_tool_errors",
]