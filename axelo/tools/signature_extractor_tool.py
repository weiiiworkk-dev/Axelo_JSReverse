"""
Signature Extractor Tool - Wrapper for SignatureExtractor

Provides SignatureExtractor as a registered tool in the tool registry.
"""
from __future__ import annotations

from typing import Any

import structlog

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

log = structlog.get_logger(__name__)


class SignatureExtractorTool(BaseTool):
    """Tool wrapper for SignatureExtractor"""
    
    def __init__(self):
        super().__init__()
        from axelo.tools.signature_extractor import SignatureExtractor
        self._extractor = SignatureExtractor()
    
    @property
    def name(self) -> str:
        return "signature_extractor"
    
    @property
    def description(self) -> str:
        return "Extract signature keys from JavaScript code"
    
    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.ANALYSIS,
            input_schema=[
                ToolInput(name="js_code", type="string", description="JavaScript code to analyze"),
                ToolInput(name="api_endpoints", type="array", description="Detected API endpoints", required=False),
            ],
            output_schema=[
                ToolOutput(name="key_source", type="string", description="hardcoded/api/computed/unknown"),
                ToolOutput(name="key_value", type="string", description="Extracted key value"),
                ToolOutput(name="algorithm", type="string", description="Detected algorithm"),
                ToolOutput(name="param_format", type="string", description="Parameter format"),
                ToolOutput(name="confidence", type="number", description="Confidence 0-1"),
                ToolOutput(name="details", type="object", description="Additional details"),
            ],
            timeout_seconds=30,
            retry_enabled=True,
            max_retries=2,
        )
    
    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        js_code = input_data.get("js_code", "")
        api_endpoints = input_data.get("api_endpoints") or input_data.get("endpoints") or []
        
        if not js_code:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: js_code"
            )
        
        try:
            result = await self._extractor.extract(js_code, api_endpoints)
            
            log.info("signature_extraction_complete",
                key_source=result.get("key_source"),
                confidence=result.get("confidence"))
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=result,
            )
            
        except Exception as e:
            log.error("signature_extraction_failed", error=str(e))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )
        finally:
            await self._extractor.close()


# Register the tool
try:
    from axelo.tools.base import get_registry
    get_registry().register(SignatureExtractorTool())
    log.info("signature_extractor_tool_registered")
except Exception as e:
    log.warning("signature_extractor_tool_register_failed", error=str(e))


__all__ = ["SignatureExtractorTool"]
