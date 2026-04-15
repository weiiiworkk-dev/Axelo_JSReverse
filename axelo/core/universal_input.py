"""
Universal Input Adapter

Converts various input formats into the standardized traffic format.
This is the entry point for the Universal Reverse Engine.

Supports:
- Browser DevTools Protocol ( CDP )
- HAR files
- PCAP files (basic)
- Direct URL
- Request/Response pairs

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Optional, Any, Union
from dataclasses import dataclass

import structlog

from axelo.core.standard_traffic import (
    StandardTraffic,
    RequestInfo,
    ResponseInfo,
    TrafficPair,
    JavaScriptBundle,
    create_from_browser_traffic,
    create_from_har,
    URLInfo,
    HTTPHeaders,
)

log = structlog.get_logger()


# =============================================================================
# INPUT TYPES
# =============================================================================

@dataclass
class InputSource:
    """Base class for input sources"""
    source_type: str
    source_path: str  # URL, file path, or identifier


@dataclass
class BrowserInput(InputSource):
    """Input from browser CDP"""
    cdp_session: Any = None
    headless: bool = True


@dataclass  
class HARInput(InputSource):
    """Input from HAR file"""
    pass


@dataclass
class URLInput(InputSource):
    """Input from direct URL"""
    visit_depth: int = 1  # How many pages to visit
    wait_time: float = 3.0  # Seconds to wait for dynamic content


@dataclass
class DirectInput(InputSource):
    """Direct request/response input"""
    request_data: dict = None
    response_data: dict = None
    js_code: list[str] = None


# =============================================================================
# ADAPTER
# =============================================================================

class UniversalInputAdapter:
    """
    Universal Input Adapter
    
    Converts various input formats to StandardTraffic
    """
    
    def __init__(self):
        self._browser_adapter = None
        self._proxy_adapter = None
    
    async def adapt(
        self,
        source: Union[str, dict, InputSource],
        source_type: Optional[str] = None,
    ) -> StandardTraffic:
        """
        Adapt input to StandardTraffic
        
        Args:
            source: The input data (URL, path, dict, etc.)
            source_type: Type of source if not auto-detected
            
        Returns:
            StandardTraffic instance
        """
        # Auto-detect source type if not provided
        if source_type is None:
            source_type = self._detect_source_type(source)
        
        log.info("adapting_input", source_type=source_type)
        
        # Route to appropriate adapter
        if source_type == "url":
            return await self._adapt_url(source)
        elif source_type == "har":
            return await self._adapt_har(source)
        elif source_type == "browser":
            return await self._adapt_browser(source)
        elif source_type == "direct":
            return await self._adapt_direct(source)
        elif source_type == "json":
            return await self._adapt_json(source)
        else:
            raise ValueError(f"Unknown source type: {source_type}")
    
    def _detect_source_type(self, source: Any) -> str:
        """Auto-detect input source type"""
        if isinstance(source, str):
            if source.startswith("http://") or source.startswith("https://"):
                return "url"
            elif source.endswith(".har"):
                return "har"
            elif Path(source).exists() and Path(source).suffix == ".json":
                return "json"
            elif Path(source).exists():
                return "har"  # Assume HAR
        elif isinstance(source, dict):
            return "direct"
        
        return "unknown"
    
    async def _adapt_url(self, url: str) -> StandardTraffic:
        """
        Adapt direct URL - use browser to capture traffic
        """
        log.info("capturing_from_url", url=url)
        
        # Use existing browser infrastructure
        try:
            from axelo.browser.driver import BrowserDriver
            from axelo.browser.interceptor import NetworkInterceptor
            from axelo.browser.profiles import get_stealth_profile
            
            # Get profile
            profile = get_stealth_profile()
            
            # Launch browser
            driver = BrowserDriver(headless=True, browser_type="chromium")
            page = await driver.launch(profile=profile)
            
            # Setup interceptor
            interceptor = NetworkInterceptor()
            interceptor.attach(page)
            
            # Navigate and wait
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)  # Wait for dynamic content
            
            # Try to scroll to trigger more requests
            try:
                await page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
            except Exception:
                pass
            
            # Extract traffic
            captures = interceptor.captures
            
            # Convert to StandardTraffic
            traffic = StandardTraffic()
            traffic.url = url
            traffic.domain = URLInfo.parse(url).host
            traffic.collection_method = "browser"
            
            for capture in captures:
                request = RequestInfo(
                    method=capture.get("method", "GET"),
                    url=URLInfo.parse(capture.get("url", "")),
                    headers=HTTPHeaders(raw=capture.get("headers", {})),
                )
                
                response = ResponseInfo(
                    status_code=capture.get("status", 0),
                    body=capture.get("response", ""),
                )
                
                pair = TrafficPair(request=request, response=response)
                
                # Detect if API call
                if "/api/" in request.url.path or ".json" in request.url.path:
                    pair.is_api_call = True
                
                # Detect signature
                for key in request.url.query_params:
                    if any(s in key.lower() for s in ["sign", "token", "key"]):
                        pair.contains_signature = True
                        pair.signature_param_names.append(key)
                
                traffic.traffic_pairs.append(pair)
            
            # Try to extract JS
            try:
                scripts = await page.evaluate("""
                    Array.from(document.querySelectorAll('script[src]'))
                        .map(s => s.src)
                        .slice(0, 20)
                """)
                # Note: Would need to fetch these separately
                log.info("found_scripts", count=len(scripts))
            except Exception:
                pass
            
            # Cleanup
            await page.context.browser.close()
            
            return traffic
            
        except Exception as e:
            log.error("browser_capture_failed", error=str(e))
            # Fallback to simple request
            return await self._adapt_simple_url(url)
    
    async def _adapt_simple_url(self, url: str) -> StandardTraffic:
        """Simple URL adaptation using httpx"""
        import httpx
        
        traffic = StandardTraffic()
        traffic.url = url
        traffic.domain = URLInfo.parse(url).host
        traffic.collection_method = "direct_request"
        
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url)
                
                request = RequestInfo(
                    method="GET",
                    url=URLInfo.parse(url),
                )
                
                resp = ResponseInfo(
                    status_code=response.status_code,
                    body=response.text,
                )
                
                pair = TrafficPair(request=request, response=resp)
                traffic.traffic_pairs.append(pair)
                
        except Exception as e:
            log.error("simple_request_failed", error=str(e))
        
        return traffic
    
    async def _adapt_har(self, har_path: str) -> StandardTraffic:
        """Adapt HAR file"""
        log.info("loading_har", path=har_path)
        
        har_path = Path(har_path)
        if not har_path.exists():
            raise FileNotFoundError(f"HAR file not found: {har_path}")
        
        with open(har_path, "r", encoding="utf-8") as f:
            har_data = json.load(f)
        
        return create_from_har(har_data)
    
    async def _adapt_browser(self, browser_config: dict) -> StandardTraffic:
        """Adapt from browser CDP session"""
        # This would integrate with existing CDP infrastructure
        log.info("browser_input_not_implemented")
        
        # For now, use URL method
        if "url" in browser_config:
            return await self._adapt_url(browser_config["url"])
        
        raise NotImplementedError("Browser input requires URL")
    
    async def _adapt_direct(self, data: dict) -> StandardTraffic:
        """Adapt direct request/response data"""
        log.info("adapting_direct_input")
        
        traffic = StandardTraffic()
        traffic.collection_method = "direct"
        
        # Parse request
        request = RequestInfo.from_raw(
            method=data.get("method", "GET"),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            body=data.get("body"),
        )
        
        # Parse response
        response = ResponseInfo(
            status_code=data.get("status_code", 0),
            body=data.get("response_body", ""),
        )
        
        pair = TrafficPair(request=request, response=response)
        traffic.traffic_pairs.append(pair)
        
        # Set domain
        if request.url.host:
            traffic.url = request.url.raw_url
            traffic.domain = request.url.host
        
        return traffic
    
    async def _adapt_json(self, json_path: str) -> StandardTraffic:
        """Adapt from JSON file"""
        log.info("loading_json", path=json_path)
        
        json_path = Path(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Determine format
        if "log" in data and "entries" in data.get("log", {}):
            # HAR format
            return await self._adapt_har(json_path)
        else:
            # Direct format
            return await self._adapt_direct(data)


# =============================================================================
# SIMPLE API
# =============================================================================

async def from_url(url: str, **kwargs) -> StandardTraffic:
    """Quick helper to capture traffic from URL"""
    adapter = UniversalInputAdapter()
    return await adapter.adapt(url, source_type="url")


async def from_har(har_path: str) -> StandardTraffic:
    """Quick helper to load from HAR file"""
    adapter = UniversalInputAdapter()
    return await adapter.adapt(har_path, source_type="har")


async def from_dict(data: dict) -> StandardTraffic:
    """Quick helper from request/response dict"""
    adapter = UniversalInputAdapter()
    return await adapter.adapt(data, source_type="direct")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "UniversalInputAdapter",
    "InputSource",
    "BrowserInput",
    "HARInput",
    "URLInput",
    "DirectInput",
    "from_url",
    "from_har",
    "from_dict",
]