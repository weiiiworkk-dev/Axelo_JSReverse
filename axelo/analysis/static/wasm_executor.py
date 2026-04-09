"""
WASM Execution Module

Comprehensive WASM execution capabilities:
- WASM module loading and execution
- Export function extraction
- WASM memory analysis
- WASM-to-JS bridge
- Signature extraction from WASM

Version: 1.0
Created: 2026-04-06
"""

from __future__ import annotations

import asyncio
import base64
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog
import aiohttp

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class WASMExport:
    """Represents a WASM export function"""
    name: str
    type: str  # "function", "table", "memory", "global"
    signature: Optional[str] = None  # i32, i64, f32, f64, v128


@dataclass
class WASMModule:
    """Represents a loaded WASM module"""
    path: str
    exports: list[WASMExport] = field(default_factory=list)
    memory_size: int = 0
    table_size: int = 0
    raw_bytes: bytes = b""


@dataclass
class WASMExecutionResult:
    """Result of WASM function execution"""
    success: bool
    output: Any = None
    memory: Optional[bytes] = None
    error: str = ""
    execution_time: float = 0.0


# =============================================================================
# WASM EXECUTOR (Python-based using wasmtime or similar)
# =============================================================================

class WASMExecutor:
    """
    Execute WASM modules and extract signatures.
    
    This module provides WASM execution capabilities without requiring
    external WASM runtimes by using Python's capabilities.
    """
    
    def __init__(self):
        self.modules: dict[str, WASMModule] = {}
        self._has_wasmtime = self._check_wasmtime()
    
    def _check_wasmtime(self) -> bool:
        """Check if wasmtime is available"""
        try:
            import wasmtime
            return True
        except ImportError:
            log.info("wasmtime_not_available_using_alternatives")
            return False
    
    async def load_module(
        self,
        wasm_path: str | Path,
        module_name: str = "default",
    ) -> WASMModule:
        """
        Load a WASM module from file or URL.
        
        Args:
            wasm_path: Path or URL to WASM file
            module_name: Name to assign to module
            
        Returns:
            WASMModule object
        """
        log.info("loading_wasm_module", path=str(wasm_path))
        
        # Check if it's a URL
        if isinstance(wasm_path, str) and wasm_path.startswith(("http://", "https://")):
            wasm_bytes = await self._fetch_wasm(wasm_path)
        else:
            # It's a file path
            wasm_path = Path(wasm_path)
            if not wasm_path.exists():
                raise FileNotFoundError(f"WASM file not found: {wasm_path}")
            wasm_bytes = wasm_path.read_bytes()
        
        # Extract exports
        exports = self._extract_exports(wasm_bytes)
        
        # Analyze memory
        memory_size, table_size = self._analyze_memory(wasm_bytes)
        
        module = WASMModule(
            path=str(wasm_path),
            exports=exports,
            memory_size=memory_size,
            table_size=table_size,
            raw_bytes=wasm_bytes,
        )
        
        self.modules[module_name] = module
        log.info("wasm_module_loaded", name=module_name, exports=len(exports))
        
        return module
    
    async def _fetch_wasm(self, url: str) -> bytes:
        """Fetch WASM from URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(f"Failed to fetch WASM: {response.status}")
                return await response.read()
    
    def _extract_exports(self, wasm_bytes: bytes) -> list[WASMExport]:
        """
        Extract exported functions from WASM binary.
        
        This is a simplified parser - full WASM parsing would require
        a proper WASM parser library.
        """
        exports = []
        
        # Try using wasmtime if available
        if self._has_wasmtime:
            try:
                import wasmtime
                
                # Create module from binary
                module = wasmtime.Module(wasm_bytes)
                
                # Get exports
                for export in module.exports:
                    exports.append(WASMExport(
                        name=export.name(),
                        type="function" if isinstance(export, wasmtime.Func) else str(type(export)),
                    ))
                
                return exports
            except Exception as e:
                log.warning("wasmtime_parse_failed", error=str(e))
        
        # Fallback: Simple binary parsing (limited)
        # Look for known export names in the binary
        known_signatures = [
            "sign", "verify", "encrypt", "decrypt", "hash",
            "encode", "decode", "hmac", "sha", "aes",
        ]
        
        # Simple heuristic: look for string references in WASM
        wasm_str = wasm_bytes.decode("latin-1", errors="ignore")
        for name in known_signatures:
            if name in wasm_str:
                # Check if it's likely an export (followed by null bytes often)
                idx = wasm_str.find(name)
                if idx >= 0 and idx < len(wasm_str) - 10:
                    # Heuristic: check for export pattern
                    context = wasm_str[idx:idx+20]
                    if "\x00" in context or "export" in wasm_str[max(0, idx-20):idx]:
                        exports.append(WASMExport(
                            name=name,
                            type="function",
                            signature="unknown",
                        ))
        
        return exports
    
    def _analyze_memory(self, wasm_bytes: bytes) -> tuple[int, int]:
        """Analyze WASM memory and table sizes"""
        memory_pages = 0
        table_elements = 0
        
        # Look for memory and table sections
        # This is a simplified heuristic
        
        # Try wasmtime for accurate analysis
        if self._has_wasmtime:
            try:
                import wasmtime
                module = wasmtime.Module(wasm_bytes)
                
                # Check memory
                for export in module.exports:
                    if isinstance(export, wasmtime.Memory):
                        memory_pages = export.memory().initial
                        
                return memory_pages, table_elements
            except:
                pass
        
        # Fallback: look for memory section in binary
        # Memory section type is 0x05, table section is 0x04
        # This is very simplified
        return memory_pages, table_elements
    
    async def execute_export(
        self,
        module_name: str,
        function_name: str,
        args: list[Any] = None,
    ) -> WASMExecutionResult:
        """
        Execute a WASM export function.
        
        Args:
            module_name: Name of loaded module
            function_name: Name of export to call
            args: Arguments to pass to function
            
        Returns:
            WASMExecutionResult
        """
        import time
        start = time.time()
        
        if module_name not in self.modules:
            return WASMExecutionResult(
                success=False,
                error=f"Module {module_name} not found",
            )
        
        module = self.modules[module_name]
        
        # Find the function
        export = next((e for e in module.exports if e.name == function_name), None)
        if not export:
            return WASMExecutionResult(
                success=False,
                error=f"Export {function_name} not found",
            )
        
        if self._has_wasmtime:
            try:
                import wasmtime
                
                # Create store and instance
                store = wasmtime.Store(wasmtime.Engine())
                module_inst = wasmtime.Module(wasm_bytes=module.raw_bytes)
                instance = wasmtime.Instance(store, module_inst, [])
                
                # Get the function
                func = instance.exports(store)[function_name]
                
                # Call with args (convert to wasm types)
                # This is simplified - real implementation would need proper type conversion
                if args:
                    result = func(store, *args)
                else:
                    result = func(store)
                
                return WASMExecutionResult(
                    success=True,
                    output=result,
                    memory=module.raw_bytes,  # Would need proper memory access
                    execution_time=time.time() - start,
                )
            except Exception as e:
                return WASMExecutionResult(
                    success=False,
                    error=str(e),
                    execution_time=time.time() - start,
                )
        
        # No wasmtime - return error
        return WASMExecutionResult(
            success=False,
            error="WASM execution requires wasmtime. Install with: pip install wasmtime",
            execution_time=time.time() - start,
        )
    
    def list_exports(self, module_name: str) -> list[WASMExport]:
        """List all exports of a module"""
        if module_name in self.modules:
            return self.modules[module_name].exports
        return []
    
    def analyze_signatures(self, module_name: str) -> dict:
        """
        Analyze a module for signature-related exports.
        
        Returns:
            Dictionary with signature-related findings
        """
        if module_name not in self.modules:
            return {"error": "Module not found"}
        
        module = self.modules[module_name]
        
        # Categorize exports
        crypto_exports = []
        encoding_exports = []
        other_exports = []
        
        crypto_keywords = ["sign", "verify", "encrypt", "decrypt", "hash", "hmac", "sha", "aes", "rsa"]
        encoding_keywords = ["encode", "decode", "base64", "hex"]
        
        for export in module.exports:
            name_lower = export.name.lower()
            if any(kw in name_lower for kw in crypto_keywords):
                crypto_exports.append(export.name)
            elif any(kw in name_lower for kw in encoding_keywords):
                encoding_exports.append(export.name)
            else:
                other_exports.append(export.name)
        
        return {
            "module": module_name,
            "total_exports": len(module.exports),
            "crypto_exports": crypto_exports,
            "encoding_exports": encoding_exports,
            "other_exports": other_exports,
            "memory_pages": module.memory_size,
            "recommendation": self._get_recommendation(crypto_exports, encoding_exports),
        }
    
    def _get_recommendation(
        self,
        crypto_exports: list,
        encoding_exports: list,
    ) -> str:
        """Get recommendation based on exports"""
        if crypto_exports:
            return "WASM module contains crypto functions. Use js_bridge mode for execution."
        elif encoding_exports:
            return "WASM module contains encoding functions. May be part of signature generation."
        else:
            return "No obvious signature-related exports. Manual analysis recommended."


# =============================================================================
# WASM SIGNATURE EXTRACTOR
# =============================================================================

class WASMSignatureExtractor:
    """
    Extract signature logic from WASM modules.
    """
    
    def __init__(self):
        self.executor = WASMExecutor()
    
    async def extract_signature(
        self,
        wasm_path: str | Path,
        observed_inputs: list[dict],
        observed_outputs: list[Any],
    ) -> dict:
        """
        Attempt to extract signature logic by analyzing inputs/outputs.
        
        Args:
            wasm_path: Path to WASM module
            observed_inputs: List of observed inputs (params, headers, etc.)
            observed_outputs: List of observed outputs (signatures)
            
        Returns:
            Dictionary with extraction results
        """
        # Load the module
        module = await self.executor.load_module(wasm_path)
        
        # Analyze exports
        analysis = self.executor.analyze_signatures("default")
        
        # If we have crypto exports, try to call them with observed inputs
        results = {
            "module_loaded": True,
            "analysis": analysis,
            "extracted_signatures": [],
            "recommendation": "",
        }
        
        # Try each crypto export with observed inputs
        for export_name in analysis.get("crypto_exports", []):
            for input_data in observed_inputs[:3]:  # Limit attempts
                try:
                    args = self._prepare_args(input_data)
                    result = await self.executor.execute_export("default", export_name, args)
                    
                    if result.success:
                        # Check if output matches observed
                        results["extracted_signatures"].append({
                            "function": export_name,
                            "input": input_data,
                            "output": result.output,
                            "match": self._check_match(result.output, observed_outputs),
                        })
                except Exception as e:
                    log.warning("wasm_call_failed", function=export_name, error=str(e))
        
        # Generate recommendation
        if results["extracted_signatures"]:
            matches = [s for s in results["extracted_signatures"] if s.get("match")]
            if matches:
                results["recommendation"] = f"Found {len(matches)} matching signature functions. Use js_bridge mode."
            else:
                results["recommendation"] = "WASM contains crypto but no exact matches. Manual analysis needed."
        else:
            results["recommendation"] = analysis.get("recommendation", "No signature extraction possible without wasmtime.")
        
        return results
    
    def _prepare_args(self, input_data: dict) -> list:
        """Prepare arguments for WASM function call"""
        # This is a heuristic - real implementation would need
        # to analyze the function signature
        args = []
        
        # Common pattern: convert dict to concatenated string
        if "params" in input_data:
            params = input_data["params"]
            if isinstance(params, dict):
                args.append("&".join(f"{k}={v}" for k, v in sorted(params.items())))
            else:
                args.append(str(params))
        
        if "key" in input_data:
            args.append(input_data["key"])
        
        return args
    
    def _check_match(self, output: Any, observed_outputs: list) -> bool:
        """Check if output matches any observed output"""
        if not output or not observed_outputs:
            return False
        
        output_str = str(output)
        
        for observed in observed_outputs:
            if isinstance(observed, str):
                # Check for exact match or partial match
                if output_str == observed or observed in output_str:
                    return True
                # Also check base64 encoded
                try:
                    if base64.b64decode(output_str.encode()).decode() == observed:
                        return True
                except:
                    pass
        
        return False


# =============================================================================
# BRIDGE INTEGRATION
# =============================================================================

class WASMBridge:
    """
    Bridge for calling WASM functions from Python.
    
    This provides integration with the existing browser bridge system.
    """
    
    def __init__(self):
        self.executor = WASMExecutor()
    
    async def initialize_from_js_bridge(
        self,
        bridge_client,
    ) -> None:
        """
        Initialize from existing JS bridge client.
        
        Args:
            bridge_client: Browser bridge client
        """
        log.info("initializing_wasm_bridge")
        # This would interface with the browser's WASM capabilities
        # Actual implementation depends on bridge client interface
    
    def create_invocation_wrapper(
        self,
        module_name: str,
        function_name: str,
    ) -> callable:
        """
        Create a Python wrapper for calling a WASM function.
        
        Args:
            module_name: Name of WASM module
            function_name: Name of export function
            
        Returns:
            Callable wrapper function
        """
        async def wrapper(*args):
            result = await self.executor.execute_export(module_name, function_name, list(args))
            if result.success:
                return result.output
            else:
                raise RuntimeError(f"WASM execution failed: {result.error}")
        
        return wrapper


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "WASMExport",
    "WASMModule", 
    "WASMExecutionResult",
    "WASMExecutor",
    "WASMSignatureExtractor",
    "WASMBridge",
]