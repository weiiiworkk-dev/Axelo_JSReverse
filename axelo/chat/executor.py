"""
Tool Executor - 工具执行引擎

负责真正执行 MCP Tools，处理工具调用、状态传递、错误处理
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from axelo.tools.base import ToolResult, ToolState, ToolStatus, get_registry
from axelo.config import settings
import structlog

log = structlog.get_logger()
DEBUG_LOG_PATH = (
    (settings.workspace / "debug-8ca886.log")
    if hasattr(settings, "workspace")
    else Path("debug-8ca886.log")
)
DEBUG_SESSION_ID = "8ca886"


@dataclass
class ExecutionContext:
    """执行上下文"""
    initial_input: dict[str, Any] = field(default_factory=dict)
    current_tool: str = ""
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    session_id: str = ""
    
    def add_result(self, tool_name: str, result: ToolResult) -> None:
        self.tool_results[tool_name] = result
        self.history.append(tool_name)
    
    def get_result(self, tool_name: str) -> ToolResult | None:
        return self.tool_results.get(tool_name)
    
    def get_all_outputs(self) -> dict[str, dict[str, Any]]:
        return {
            name: result.output 
            for name, result in self.tool_results.items()
            if result.success
        }


class ToolExecutor:
    def __init__(self, registry=None):
        self.registry = registry or get_registry()
        self.state = ToolState()
        self.ctx = ExecutionContext()
        self._checkpoint_dir = settings.workspace / "checkpoints" if hasattr(settings, "workspace") else None
    
    def _debug_log(self, run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
        """Append one NDJSON debug record for runtime diagnosis."""
        payload = {
            "sessionId": DEBUG_SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        try:
            with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            # Debug logging must never interrupt tool execution.
            pass
    
    async def execute_tool(self, tool_name, input_data=None) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            log.error("tool_not_found", tool=tool_name)
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.FAILED,
                error="Tool not found"
            )
        
        merged_input = {**(input_data or {}), **self.state.context}
        
        try:
            # #region agent log
            if tool_name == "static":
                run_id = self.ctx.session_id or "run"
                self._debug_log(
                    run_id=run_id,
                    hypothesis_id="H2",
                    location="axelo/chat/executor.py:execute_tool",
                    message="about to run static tool",
                    data={
                        "has_js_code": bool((input_data or {}).get("js_code")),
                        "has_content": bool((input_data or {}).get("content")),
                        "bundles_count": len((input_data or {}).get("bundles") or []),
                        "input_keys": sorted(list((input_data or {}).keys())),
                    },
                )
            # #endregion
            result = await tool.run(merged_input, self.state)
            if result.success:
                self.state.save_result(result)
                self.ctx.add_result(tool_name, result)
                log.info("tool_executed", tool=tool_name, status=result.status.value)
                # #region agent log
                if tool_name == "fetch":
                    run_id = self.ctx.session_id or "run"
                    self._debug_log(
                        run_id=run_id,
                        hypothesis_id="H3",
                        location="axelo/chat/executor.py:execute_tool",
                        message="fetch succeeded output shape",
                        data={
                            "output_keys": sorted(list((result.output or {}).keys())),
                            "content_len": len((result.output or {}).get("content") or ""),
                            "content_type": (result.output or {}).get("content_type"),
                        },
                    )
                # #endregion
            else:
                log.warning("tool_failed", tool=tool_name, error=result.error)
                # #region agent log
                run_id = self.ctx.session_id or "run"
                self._debug_log(
                    run_id=run_id,
                    hypothesis_id="H4",
                    location="axelo/chat/executor.py:execute_tool",
                    message="tool execution failed",
                    data={
                        "tool_name": tool_name,
                        "error": result.error,
                    },
                )
                # #endregion
            return result
        except Exception as exc:
            log.error("tool_execution_error", tool=tool_name, error=str(exc))
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.FAILED,
                error=str(exc)
            )
    
    async def execute_sequence(self, tool_sequence, initial_input=None, stop_on_error=True, session_id=None):
        self.ctx = ExecutionContext(initial_input=initial_input or {}, session_id=session_id or "")
        results = {}
        
        log.info("executing_sequence", tools=tool_sequence)
        # #region agent log
        run_id = self.ctx.session_id or "run"
        self._debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="axelo/chat/executor.py:execute_sequence",
            message="sequence started",
            data={
                "tool_sequence": list(tool_sequence),
                "initial_input_keys": sorted(list((initial_input or {}).keys())),
                "initial_has_url": bool((initial_input or {}).get("url")),
                "initial_has_goal": bool((initial_input or {}).get("goal")),
            },
        )
        # #endregion
        
        # Save checkpoint before starting
        if session_id:
            self._save_checkpoint("start", {"tools": tool_sequence})
        
        for tool_name in tool_sequence:
            input_data = self._build_input(tool_name, initial_input)
            result = await self.execute_tool(tool_name, input_data)
            results[tool_name] = result
            
            # Save checkpoint after each tool
            if session_id:
                self._save_checkpoint(tool_name, {
                    "tool": tool_name,
                    "success": result.success,
                    "output": result.output if result.success else None,
                    "error": result.error,
                })
            
            if not result.success:
                log.warning("tool_failed_in_sequence", tool=tool_name)
                if stop_on_error:
                    break
            
            total_time = sum(r.duration_seconds for r in results.values())
            if total_time > 300:
                log.warning("sequence_timeout", total_time=total_time)
                break
        
        # Save final checkpoint
        if session_id:
            self._save_checkpoint("complete", {"results": {k: v.status.value for k, v in results.items()}})
        
        return results
    
    def _build_input(self, tool_name, initial_input):
        merged = dict(initial_input)
        for prev_name, prev_result in self.ctx.tool_results.items():
            if prev_result.success:
                merged.update(prev_result.output)
        if tool_name == "web_search" and not merged.get("query"):
            goal = str(merged.get("goal") or "").strip()
            url = str(merged.get("url") or "").strip()
            domain = ""
            if url:
                parsed = urlparse(url)
                domain = parsed.netloc or parsed.path
            query_parts = [part for part in [domain, goal] if part]
            if query_parts:
                merged["query"] = " ".join(query_parts).strip()
        if tool_name == "browser" and not merged.get("url"):
            results = merged.get("results") or []
            resolved_url = ""
            if isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                resolved_url = str(first.get("url") or "").strip()
            if resolved_url:
                merged["url"] = resolved_url
        if tool_name == "fetch" and not merged.get("url"):
            page_url = str(merged.get("page_url") or "").strip()
            fallback_url = ""
            if page_url:
                fallback_url = page_url
            else:
                results = merged.get("results") or []
                if isinstance(results, list) and results:
                    first = results[0] if isinstance(results[0], dict) else {}
                    fallback_url = str(first.get("url") or "").strip()
            if fallback_url:
                merged["url"] = fallback_url
        # #region agent log
        run_id = self.ctx.session_id or "run"
        self._debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="axelo/chat/executor.py:_build_input",
            message="built tool input",
            data={
                "tool_name": tool_name,
                "keys": sorted(list(merged.keys())),
                "has_js_code": bool(merged.get("js_code")),
                "has_content": bool(merged.get("content")),
                "bundles_count": len(merged.get("bundles") or []),
                "content_len": len(merged.get("content") or ""),
            },
        )
        # #endregion
        return merged
    
    def _save_checkpoint(self, stage: str, data: dict) -> None:
        """Save execution checkpoint"""
        if not self._checkpoint_dir:
            return
        
        try:
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_file = self._checkpoint_dir / f"{self.ctx.session_id}_{stage}.json"
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump({
                    "stage": stage,
                    "session_id": self.ctx.session_id,
                    "history": self.ctx.history,
                    "data": data,
                }, f, ensure_ascii=False, indent=2)
            log.debug("checkpoint_saved", stage=stage, session=self.ctx.session_id)
        except Exception as e:
            log.warning("checkpoint_save_failed", error=str(e))
    
    def load_checkpoint(self, session_id: str) -> dict | None:
        """Load checkpoint for resuming"""
        if not self._checkpoint_dir:
            return None
        
        try:
            checkpoint_file = self._checkpoint_dir / f"{session_id}_complete.json"
            if checkpoint_file.exists():
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            log.warning("checkpoint_load_failed", error=str(e))
        
        return None
    
    def get_state(self):
        return self.state
    
    def get_results(self):
        return self.ctx.tool_results
    
    def get_outputs(self):
        return self.ctx.get_all_outputs()
    
    def reset(self):
        self.state = ToolState()
        self.ctx = ExecutionContext()


def create_executor():
    return ToolExecutor()
