"""
Axelo API Scanner - Scan and discover APIs from target website
"""

import asyncio
import time
import re
import random
from dataclasses import dataclass, field

import structlog
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from axelo.config import settings

log = structlog.get_logger()
console = Console()


@dataclass
class ScanResult:
    """API scan result"""
    site: str
    url: str
    apis: list = field(default_factory=list)
    total_requests: int = 0
    duration: float = 0.0
    error: str = ""


class APIScanner:
    """API Scanner - discovers APIs from target website"""
    
    # Generic third-party domains (used by ALL sites)
    THIRD_PARTY_DOMAINS = {
        # Google ecosystem
        "google-analytics.com",
        "googletagmanager.com",
        "doubleclick.net",
        "google.com",
        "gstatic.com",
        "googleusercontent.com",
        "googlesyndication.com",
        # Facebook ecosystem
        "facebook.net",
        "facebook.com",
        "instagram.com",
        "messenger.com",
        # Other common tracking
        "criteo.com",
        "taboola.com",
        "outbrain.com",
        "amazon-adsystem.com",
        "advertising.com",
        "bing.com",
        "yahoo.com",
        "scorecardresearch.com",
        "quantserve.com",
        "hotjar.com",
        "mixpanel.com",
        "segment.com",
        "amplitude.com",
        # Analytics
        "analytics.google.com",
        "stats.g.doubleclick.net",
        # Tag managers
        "connect.facebook.net",
        # Amazon specific (treated as third-party for non-Amazon sites)
        "amazon-adsystem.com",
    }
    
    # Generic API type priority (used by ALL sites)
    API_TYPE_PRIORITY = {
        "search_results": 100,
        "product_listing": 90,
        "product_detail": 85,
        "reviews": 80,
        "user": 70,
        "cart": 60,
        "payment": 55,
        "video": 50,
        "unknown": 40,
    }
    
    async def quick_scan(self, site: str, url: str, search_query: str = None) -> ScanResult:
        """
        Quick scan - capture requests and discover APIs
        
        Args:
            site: Site name (e.g., "amazon")
            url: Resolved URL (e.g., "https://www.amazon.com")
            search_query: Optional search query to navigate to specific content
        """
        start_time = time.time()
        
        result = ScanResult(site=site, url=url)
        
        try:
            from axelo.browser.driver import BrowserDriver
            from axelo.browser.interceptor import NetworkInterceptor
            from axelo.browser.profiles import PROFILES
            
            # Get default profile - use stealth profile for anti-detection
            from axelo.browser.profiles import get_stealth_profile
            profile = get_stealth_profile()
            
            # Show progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task(f"[cyan]Scanning {site}...", total=100)
                
                # Launch browser (with fallback for crash recovery)
                progress.update(task, description=f"[cyan]Launching browser...", completed=10)
                log.info("launching_browser", url=url)
                
                # Try regular driver first, fallback to enhanced if needed
                driver = None
                page = None
                launch_error = None
                
                # Try 1: Regular BrowserDriver
                try:
                    driver = BrowserDriver(headless=True, browser_type="chromium")
                    page = await driver.launch(profile=profile, trace_path=None)
                    log.info("browser_launched_success", method="regular")
                except Exception as e:
                    launch_error = str(e)
                    log.warning("browser_launch_failed_trying_enhanced", error=launch_error)
                    driver = None
                    
                    # Try 2: Enhanced BrowserDriver as fallback
                    try:
                        from axelo.browser.enhanced_driver import EnhancedBrowserDriver
                        driver = EnhancedBrowserDriver(headless=True, browser_type="chromium", enable_fingerprint=False)
                        async with driver:
                            page = await driver.launch(profile=profile, trace_path=None)
                            log.info("browser_launched_success", method="enhanced_fallback")
                    except Exception as e2:
                        log.error("enhanced_driver_also_failed", error=str(e2))
                        # Try 3: Last resort - minimal browser with no extra args
                        try:
                            import platform
                            if platform.system() == "Windows":
                                # Windows: try without stealth args
                                from playwright.async_api import async_playwright
                                pw = await async_playwright().start()
                                browser = await pw.chromium.launch(
                                    headless=True,
                                    args=["--disable-blink-features=AutomationControlled"]
                                )
                                context = await browser.new_context()
                                page = await context.new_page()
                                driver = None  # We can't use the standard close method
                                log.info("browser_launched_success", method="minimal_fallback")
                                # Store browser/pw for cleanup
                                await pw.start()  # Keep reference
                        except Exception as e3:
                            raise Exception(f"All browser launch attempts failed: {e3}")
                
                if not page:
                    raise Exception("Failed to launch browser after all fallback attempts")
                
                # Add random viewport to simulate human
                await page.set_viewport_size({
                    "width": random.randint(1200, 1920),
                    "height": random.randint(800, 1080)
                })
                
                # Setup interceptor
                progress.update(task, description=f"[cyan]Capturing requests...", completed=20)
                interceptor = NetworkInterceptor()
                interceptor.attach(page)
                
                # Navigate to target (with retry mechanism)
                progress.update(task, description=f"[cyan]Loading {site}...", completed=30)
                log.info("navigating", url=url)
                
                nav_error = None
                for attempt in range(2):  # Max 2 attempts
                    try:
                        # Add random delay before navigation (simulate human)
                        if attempt > 0:
                            await asyncio.sleep(random.uniform(1.0, 3.0))
                        
                        # Use domcontentloaded + longer timeout
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        nav_error = None
                        break
                    except Exception as e:
                        nav_error = str(e)
                        log.warning("navigation_attempt_failed", attempt=attempt + 1, error=nav_error)
                        continue
                
                if nav_error:
                    raise Exception(f"Navigation failed after 2 attempts: {nav_error}")
                
                # NEW: If search_query is provided, perform search
                if search_query:
                    progress.update(task, description=f"[cyan]Searching for '{search_query}'...", completed=40)
                    log.info("performing_search", query=search_query)
                    try:
                        # Try to find search box and type query
                        # Different sites have different search box selectors
                        search_selectors = [
                            "input[name='keyword']",           # Generic
                            "input[name='k']",                # Amazon
                            "input[id='twotabsearchtextbox']", # Amazon
                            "input[id='search']",             # Generic
                            "input[type='search']",           # Generic
                            "input[placeholder*='Search']",   # Generic
                            "#searchInput",                   # Wikipedia
                            "input[type='text'][aria-label*='Search']", # Generic
                        ]
                        
                        search_success = False
                        for selector in search_selectors:
                            try:
                                search_box = await page.wait_for_selector(selector, timeout=3000)
                                if search_box:
                                    await search_box.fill(search_query)
                                    # Press Enter to search
                                    await search_box.press("Enter")
                                    search_success = True
                                    log.info("search_performed", query=search_query, selector=selector)
                                    break
                            except:
                                continue
                        
                        if not search_success:
                            # Fallback: try direct URL navigation
                            # Build search URL based on site
                            search_url = self._build_search_url(site, url, search_query)
                            if search_url:
                                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                                log.info("search_via_url", query=search_query, url=search_url)
                        
                        # Wait for search results to load
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        
                    except Exception as e:
                        log.warning("search_failed", error=str(e))
                        # Continue anyway - we still have initial page requests
                
                # Random delay to simulate human behavior (1-3 seconds)
                await asyncio.sleep(random.uniform(1.0, 3.0))
                
                # Try to scroll down (simulate human)
                try:
                    await page.evaluate("""() => {
                        window.scrollBy(0, Math.random() * 500);
                    }""")
                    await asyncio.sleep(0.5)
                except:
                    pass
                
                # Get captures
                progress.update(task, description=f"[cyan]Analyzing requests...", completed=70)
                captures = interceptor.captures
                result.total_requests = len(captures)
                log.info("captures_collected", count=result.total_requests)
                
                # Discover APIs
                progress.update(task, description=f"[cyan]Discovering APIs...", completed=85)
                apis = self._discover_apis(captures)
                
                # GENERIC: Data-driven API selection - rerank based on actual response
                progress.update(task, description=f"[cyan]Selecting best API...", completed=90)
                apis = self._data_driven_rerank(apis[:10]) + apis[10:]
                
                progress.update(task, description=f"[cyan]Complete!", completed=100)
            
            # Convert to UI format
            for i, api in enumerate(apis):
                ui_api = type('obj', (object,), {
                    'url': api['url'],
                    'method': api['method'],
                    'description': api.get('reason', ''),
                    'resource_type': api.get('resource_type', 'unknown'),
                    'confidence': api['confidence'],
                    'protection_signals': api.get('signals', []),
                    'index': i + 1,
                })()
                result.apis.append(ui_api)
            
            result.duration = time.time() - start_time
            
            # Close browser (handle different driver types)
            try:
                if driver and hasattr(driver, 'close'):
                    await driver.close()
                # For minimal fallback, we don't have a driver object
                # Browser cleanup would need to be handled separately
            except Exception as e:
                log.warning("browser_close_failed", error=str(e))
            
            log.info("scan_complete", apis=len(result.apis), duration=result.duration)
            
        except Exception as e:
            log.error("scan_failed", error=str(e))
            result.error = str(e)
        
        return result
    
    def print_api_table(self, apis: list) -> None:
        """Print discovered APIs as a rich table"""
        if not apis:
            console.print("[yellow]No APIs discovered.[/yellow]")
            return
        
        table = Table(title="[bold cyan]Discovered APIs[/bold cyan]", show_lines=True)
        table.add_column("#", style="cyan", width=4, justify="right")
        table.add_column("Method", style="magenta", width=6)
        table.add_column("URL", style="white")
        table.add_column("Type", style="green", width=15)
        table.add_column("Confidence", justify="right", width=12)
        
        for api in apis[:15]:  # Show top 15
            conf_pct = int(api.confidence * 100)
            conf_style = "green" if conf_pct >= 70 else "yellow" if conf_pct >= 50 else "red"
            method_style = "green" if api.method == "GET" else "magenta"
            
            # Truncate URL
            url = api.url
            if len(url) > 45:
                url = url[:42] + "..."
            
            table.add_row(
                str(api.index),
                f"[{method_style}]{api.method}[/{method_style}]",
                url,
                api.resource_type[:15],
                f"[{conf_style}]{conf_pct}%[/{conf_style}]"
            )
        
        console.print()
        console.print(table)
        
        if len(apis) > 15:
            console.print(f"[dim]... and {len(apis) - 15} more APIs[/dim]")
    
    def _discover_apis(self, captures: list) -> list:
        """
        Improved API discovery based on heuristics
        """
        import re
        
        apis = []
        
        # Protection keywords (expanded)
        PROTECTION_KEYWORDS = [
            "sign", "signature", "token", "nonce", "csrf", "verify", "auth",
            "security", "encrypt", "hash", "appkey", "secret", "t", "ts", "api"
        ]
        
        # Resource keywords (expanded)
        RESOURCE_KEYWORDS = {
            "search_results": ["search", "query", "keyword", "/s", "suggest"],
            "product_listing": ["product", "item", "/p/", "detail", "goods", "sku"],
            "product_detail": ["detail", "info", "pdp", "item"],
            "reviews": ["review", "comment", "rating", "feedback"],
            "video": ["video", "play", "feed", "bilibili"],
            "user": ["user", "profile", "account", "member"],
            "cart": ["cart", "shopping", "order"],
            "payment": ["pay", "payment", "checkout"],
        }
        
        # API path patterns
        API_PATH_PATTERNS = [
            r"/api/", r"/v1/", r"/v2/", r"/v3/", r"/rpc/", r"/gateway/",
            r"/open/", r"/web/", r"/mobile/", r"/inner/", r"/proxy/",
            r"\.json", r"\.ajax", r"/proxy/", r"/gateway/", r"/outer/",
        ]
        
        # Allowed response statuses (expanded)
        ALLOWED_STATUS = {200, 201, 204, 301, 302, 400, 401, 403, 429, 500, 502, 503}
        
        # Allowed initiators (expanded)
        ALLOWED_INITIATORS = {"fetch", "xhr", "script", "navigation", "other", ""}
        
        for capture in captures:
            url = capture.url
            url_lower = url.lower()
            
            # Skip empty URLs
            if not url or len(url) < 10:
                continue
            
            # Skip non-API domains (static resources)
            skip_domains = ['.jpg', '.jpeg', '.png', '.gif', '.css', '.woff', '.ttf', 
                          '.ico', '.svg', '.webp', '.mp4', '.mp3', '.flv']
            if any(url_lower.endswith(ext) for ext in skip_domains):
                continue
            
            # GENERIC: Skip third-party domains (used by ALL sites)
            is_third_party = False
            for domain in self.THIRD_PARTY_DOMAINS:
                if domain in url_lower:
                    is_third_party = True
                    break
            if is_third_party:
                continue
            
            confidence = 0.0
            signals = []
            reason = ""
            resource_type = "unknown"
            
            # 1. Check if URL matches API path patterns (STRONG signal)
            for pattern in API_PATH_PATTERNS:
                if re.search(pattern, url_lower):
                    confidence += 0.4
                    break
            
            # 2. Check protection signals
            for kw in PROTECTION_KEYWORDS:
                if kw in url_lower:
                    confidence += 0.15
                    if kw not in signals:
                        signals.append(kw)
            
            # 3. Check resource type
            for rt, keywords in RESOURCE_KEYWORDS.items():
                if any(kw in url_lower for kw in keywords):
                    confidence += 0.25
                    resource_type = rt
                    reason = rt.replace("_", " ").title()
                    break
            
            # 4. Check response status (positive indicator)
            if capture.response_status in ALLOWED_STATUS:
                if capture.response_status == 200:
                    confidence += 0.15
                elif capture.response_status in (401, 403):
                    # Protected endpoint - likely has signature
                    confidence += 0.2
                    signals.append("auth_required")
            
            # 5. Check HTTP method
            if capture.method == "POST":
                confidence += 0.1
            elif capture.method == "PUT":
                confidence += 0.1
            elif capture.method == "DELETE":
                confidence += 0.1
            
            # 6. Check URL length (longer URLs often have more params)
            if len(url) > 100:
                confidence += 0.05
            
            # 7. Check if it's a JSON API
            if url.endswith('.json') or 'json' in url_lower:
                confidence += 0.1
            
            # Keep APIs with confidence >= 0.2 (lowered from 0.3)
            MIN_CONFIDENCE = 0.2
            if confidence >= MIN_CONFIDENCE:
                apis.append({
                    'url': url,
                    'method': capture.method,
                    'confidence': min(confidence, 1.0),
                    'signals': signals[:5],  # Keep up to 5 signals
                    'reason': reason or "API endpoint",
                    'resource_type': resource_type,
                    'response_status': capture.response_status,
                })
        
        # GENERIC: Sort by API type priority (used by ALL sites)
        # Priority: search_results > product_listing > product_detail > reviews > user > cart > payment > unknown
        apis.sort(key=lambda x: (
            self.API_TYPE_PRIORITY.get(x['resource_type'], 40),  # Sort by type priority first
            x['confidence']  # Then by confidence
        ), reverse=True)
        
        # Post-sorting filter: demote "search suggestion" APIs that look like autocomplete
        # These APIs return suggestions/autocomplete, not actual product listings
        suggestion_patterns = ['suggest', 'autocomplete', 'predict', 'completion', 'query']
        demoted_apis = []
        kept_apis = []
        for api in apis:
            url_lower = api['url'].lower()
            # Check if this is a suggestion/autocomplete API
            is_suggestion = any(pattern in url_lower for pattern in suggestion_patterns)
            if is_suggestion and api['resource_type'] == 'search_results':
                demoted_apis.append(api)
            else:
                kept_apis.append(api)
        
        # Combine: first kept APIs (proper results), then demoted suggestions
        unique_apis = kept_apis + demoted_apis
        
        # GENERIC: Data-driven API selection for top candidates
        # Skip in sync context - will be called in async quick_scan
        # This analyzes actual response structure to select best product API
        
        return unique_apis[:30]  # Return top 30
    
    def _data_driven_rerank(self, apis: list[dict]) -> list[dict]:
        """
        Rerank APIs based on actual response data structure analysis.
        
        GENERIC: This works the SAME way for ALL sites - analyzing response
        data to determine if it contains product listings (not suggestions).
        """
        if len(apis) <= 1:
            return apis
        
        # Import here to avoid circular imports
        import httpx
        
        PRODUCT_FIELDS = {'title', 'name', 'price', 'image', 'img', 'rating', 'review', 'asin', 'sku', 'product_id', 'url', 'link'}
        SUGGESTION_FIELDS = {'suggestion', 'predict', 'autocomplete', 'query', 'text', 'label'}
        
        scored_apis = []
        
        for api in apis:
            score = 0.0
            try:
                with httpx.Client(timeout=3.0, follow_redirects=True) as client:
                    response = client.get(api['url'])
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except:
                            data = None
                        
                        if data:
                            # Analyze data structure
                            fields = []
                            record_count = 0
                            
                            if isinstance(data, list):
                                record_count = len(data)
                                if data and isinstance(data[0], dict):
                                    fields = list(data[0].keys())
                            elif isinstance(data, dict):
                                # Find data list
                                for key in ['data', 'items', 'results', 'products']:
                                    if key in data and isinstance(data[key], list):
                                        record_count = len(data[key])
                                        if data[key] and isinstance(data[key][0], dict):
                                            fields = list(data[key][0].keys())
                                        break
                                if not fields:
                                    fields = list(data.keys())
                            
                            if fields:
                                field_set = {f.lower() for f in fields}
                                
                                # Positive: has product fields
                                product_count = len(field_set & PRODUCT_FIELDS)
                                if product_count >= 2:
                                    score += 0.4
                                elif product_count >= 1:
                                    score += 0.2
                                
                                # Negative: has suggestion fields
                                suggestion_count = len(field_set & SUGGESTION_FIELDS)
                                if suggestion_count >= 2:
                                    score -= 0.3
                                elif suggestion_count >= 1:
                                    score -= 0.1
                                
                                # Positive: has URL field
                                if any(f in field_set for f in ['url', 'link', 'href', 'product_url']):
                                    score += 0.1
                                
                                # Neutral: reasonable record count
                                if 1 <= record_count <= 100:
                                    score += 0.1
            except:
                pass
            
            scored_apis.append((api, score))
        
        # Sort by score (highest first)
        scored_apis.sort(key=lambda x: x[1], reverse=True)
        
        return [api for api, _ in scored_apis]
    
    def _build_search_url(self, site: str, base_url: str, query: str) -> str:
        """
        Build search URL based on site.
        
        Args:
            site: Site name
            base_url: Base URL of the site
            query: Search query
            
        Returns:
            Search URL or None if not supported
        """
        import urllib.parse
        
        encoded_query = urllib.parse.quote(query)
        
        # Site-specific search URL patterns
        search_patterns = {
            "amazon": f"https://www.amazon.com/s?k={encoded_query}",
            "jd": f"https://search.jd.com/Search?keyword={encoded_query}",
            "taobao": f"https://s.taobao.com/search?q={encoded_query}",
            "tmall": f"https://list.tmall.com/search_product.htm?q={encoded_query}",
            "ebay": f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}",
            "walmart": f"https://www.walmart.com/search?q={encoded_query}",
            "target": f"https://www.target.com/s?searchTerm={encoded_query}",
            "bestbuy": f"https://www.bestbuy.com/site/searchpage.jsp?st={encoded_query}",
            "alibaba": f"https://www.alibaba.com/trade/search?SearchText={encoded_query}",
        }
        
        # Check if site matches any known pattern
        site_lower = site.lower()
        for key, pattern in search_patterns.items():
            if key in site_lower:
                return pattern
        
        # Generic fallback: try common search paths
        return f"{base_url.rstrip('/')}/search?q={encoded_query}"


async def scan_website(site: str) -> ScanResult:
    """
    Convenience function to scan a website
    
    Args:
        site: Site name (e.g., "jd.com")
        
    Returns:
        ScanResult with discovered APIs
    """
    # Resolve site to URL
    from axelo.wizard import _resolve_site
    url, _ = _resolve_site(site)
    
    scanner = APIScanner()
    return await scanner.quick_scan(site, url)
