"""
Tool Executor - 工具执行引擎

负责真正执行 MCP Tools，处理工具调用、状态传递、错误处理
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axelo.tools.base import ToolResult, ToolState, ToolStatus, get_registry
from axelo.config import settings
import structlog

log = structlog.get_logger()


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
            result = await tool.run(merged_input, self.state)
            if result.success:
                self.state.save_result(result)
                self.ctx.add_result(tool_name, result)
                log.info("tool_executed", tool=tool_name, status=result.status.value)
            else:
                log.warning("tool_failed", tool=tool_name, error=result.error)
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
