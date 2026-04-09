"""Axelo UI Main - Smart Crawl System"""

import asyncio
import logging
import sys

import structlog

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _setup_logging(log_level: str = "info") -> None:
    """Configure structlog to filter by log level."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
    )


_setup_logging("info")


# ============================================================================
# UI Screens
# ============================================================================

def print_welcome():
    """Print welcome banner"""
    print()
    print("  " + "=" * 61)
    print("  " + "  █████╗ ██╗  ██╗███████╗██╗      ██████╗")
    print("  " + " ██╔══██╗╚██╗██╔╝██╔════╝██║     ██╔═══██╗")
    print("  " + " ███████║ ╚███╔╝ █████╗  ██║     ██║   ██║")
    print("  " + " ██╔══██║ ██╔██╗ ██╔══╝  ██║     ██║   ██║")
    print("  " + " ██║  ██║██╔╝ ██╗███████╗███████╗╚██████╔╝")
    print("  " + " ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝")
    print("  " + "    AI-Powered JavaScript Reverse Engineering")
    print("  " + "=" * 61)
    print()
    print("  Smart Crawl System")
    print("  - Auto-discover APIs")
    print("  - Configure crawl parameters")
    print("  - Reverse + Crawl in one flow")
    print()


def print_help():
    """Print help message"""
    print()
    print("  Commands: help, status, clear, quit")
    print("  Example: jd.com, taobao.com, bilibili.com")


def show_status():
    """Show system status"""
    try:
        from axelo.config import settings
        from axelo.storage.session_store import SessionStore
        sessions = SessionStore(settings.sessions_dir).list_sessions()
        print(f"  Sessions: {len(sessions)}")
        print(f"  Workspace: {settings.workspace}")
    except:
        print("  Version: 0.1.0")


# ============================================================================
# Main Smart Crawl Workflow
# ============================================================================

async def smart_crawl_workflow(site: str, auto: bool = False):
    """
    Execute smart crawl workflow:
    1. Scan website for APIs
    2. User selects API
    3. User configures crawl parameters
    4. Execute reverse analysis
    5. Execute crawl
    """
    from rich.console import Console
    from axelo.ui.models import APICandidate, CrawlConfig
    from axelo.ui.api_scanner import scan_website, APIScanner
    from axelo.ui.interactive import (
        print_api_list,
        select_apis,
        configure_crawl,
        print_config_summary,
    )
    from axelo.ui.executor import execute_full_workflow
    from axelo.wizard import _resolve_site
    
    console = Console()
    
    # Step 1: Resolve URL
    url, _ = _resolve_site(site)
    
    print()
    console.print(f"[bold cyan]  > Scanning {site} for APIs...[/bold cyan]")
    print("  " + "-" * 50)
    
    # NEW STEP: Ask user for search query/product keyword
    search_query = None
    if not auto:
        print()
        print("  What product/keyword do you want to crawl?")
        print("  (Leave empty to scan all APIs, or enter search term)")
        search_query = input("  > ").strip()
        if search_query:
            print(f"  Search query: {search_query}")
            print()
    else:
        # In auto mode, use a default search query
        search_query = "laptop"
        console.print(f"[cyan]  Auto mode: using default search query '{search_query}'[/cyan]")
    
    # Step 2: Scan for APIs (with progress bar)
    scanner = APIScanner()
    scan_result = await scanner.quick_scan(site, url, search_query=search_query)
    
    if scan_result.error:
        console.print(f"[bold red]  Scan error: {scan_result.error}[/bold red]")
        return
    
    apis = scan_result.apis
    
    if not apis:
        console.print("[yellow]  No APIs discovered. Trying direct reverse...[/yellow]")
        # Fall back to original workflow
        await original_workflow(site, auto)
        return
    
    # Step 3: Display APIs as table and select
    scanner.print_api_table(apis)
    
    # In auto mode, select first API automatically
    if auto:
        console.print("[cyan]  Auto mode: selecting first API...[/cyan]")
        selected = [apis[0]] if apis else []
    else:
        selected = select_apis(apis)
    
    if not selected:
        print("\n  No API selected.")
        return
    
    # Use first selected API
    selected_api = selected[0]
    
    # Step 4: Configure crawl (in auto mode, use defaults)
    if auto:
        from axelo.ui.models import CrawlConfig, calculate_estimate
        config = CrawlConfig()
        config.selected_apis = [selected_api.url]
        config.content_type = "name_price"  # Default
        config.item_limit = 100  # Default
        config.crawl_rate = "medium"
        config.output_format = "json"
        config.estimated_cost, config.estimated_duration = calculate_estimate(config.item_limit, config.crawl_rate)
        console.print(f"[cyan]  Auto mode: content=name_price, scale=100, rate=medium, format=json[/cyan]")
    else:
        config = configure_crawl(selected_api)
    
    # Step 5: Confirm configuration (skip in auto mode)
    if auto:
        console.print("[cyan]  Auto mode: confirmed configuration[/cyan]")
    else:
        config = print_config_summary(site, selected_api, config)
        if not config:
            return
    
    # Step 6: Execute reverse + crawl
    print()
    print("  > Starting reverse analysis...")
    print("  (This may take a few minutes)")
    print()
    
    reverse_result, crawl_result = await execute_full_workflow(
        site=site,
        url=url,
        known_endpoint=selected_api.url,
        config=config,
    )
    
    # Step 7: Show result
    print_result(reverse_result, crawl_result, config)


def print_result(reverse_result, crawl_result, config):
    """Print final result"""
    print()
    print("  " + "=" * 50)
    print("  CRAWL COMPLETE")
    print("  " + "=" * 50)
    
    print(f"\n  Reverse Analysis:")
    print(f"    Session: {reverse_result.session_id}")
    print(f"    Verified: {'Yes' if reverse_result.verified else 'No'} ({reverse_result.verify_score}%)")
    
    if crawl_result.total > 0:
        print(f"\n  Crawl Results:")
        print(f"    Total:    {crawl_result.total}")
        print(f"    Success:  {crawl_result.success} ({crawl_result.success*100//crawl_result.total}%)")
        print(f"    Failed:   {crawl_result.failed}")
        print(f"    Duration: {crawl_result.duration:.1f}s")
        
        if crawl_result.output_path:
            print(f"\n  Output: {crawl_result.output_path}")
    
    print("\n  Done!")


async def original_workflow(site: str, auto_confirm: bool = False):
    """Original reverse-only workflow"""
    from axelo.wizard import _resolve_site
    from axelo.patterns.common import match_profile
    
    url, _ = _resolve_site(site)
    profile = match_profile(url)
    
    print()
    print(f"  > Identifying: {site}")
    print("  " + "-" * 50)
    
    items = [("Domain", url)]
    if profile:
        items.append(("Type", profile.category))
        items.append(("Algorithm", profile.typical_algorithm))
        items.append(("Difficulty", profile.difficulty))
        items.append(("Strategy", profile.strategy))
        hint = profile.analysis_hints[0] if profile.analysis_hints else "Standard"
    else:
        items.append(("Type", "generic"))
        hint = "Standard"
    
    max_key = max(len(k) for k, _ in items)
    for key, val in items:
        print(f"    * {key}:{' ' * (max_key - len(key))} {val}")
    
    print()
    mode_txt = "auto" if auto_confirm else "interactive"
    
    print("  Parameters")
    print("  " + "-" * 50)
    print(f"  URL:     {url}")
    print(f"  Goal:    Analyze signature/Token logic")
    print(f"  Mode:    {mode_txt}")
    print(f"  Budget:  2.00 USD")
    print(f"  Hint:    {hint}")
    print("  " + "-" * 50)
    print()
    
    # Confirm
    if auto_confirm:
        confirm = "y"
    else:
        confirm = input("  Confirm? [Y/n]: ").strip().lower()
    
    if confirm not in ["", "y", "yes"]:
        print("\n  Cancelled")
        return
    
    print()
    print("  > Starting reverse...")
    print()
    
    # Execute reverse
    from axelo.ui.executor import ReverseExecutor
    
    executor = ReverseExecutor()
    result = await executor.execute(
        url=url,
        budget=2.0,
    )
    
    print()
    if result.completed:
        print(f"  > Complete! Session: {result.session_id}")
        print(f"  > Verification: {result.verify_score}%")
    else:
        print(f"  > Failed: {result.error}")


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    
    if len(sys.argv) > 1:
        site = sys.argv[1]
        
        # Check commands
        if site in ["help", "-help", "--help", "h", "?", "-h", "-?"]:
            print_help()
            return
        if site in ["status", "-status", "--status"]:
            show_status()
            return
        
        auto = "--auto" in sys.argv or "-y" in sys.argv
        
        # Validate website
        is_valid = "." in site
        if not is_valid:
            is_valid = site.replace(".", "").replace("-", "").replace("_", "").replace(" ", "").isalpha()
        
        if is_valid:
            # Use smart crawl workflow
            asyncio.run(smart_crawl_workflow(site, auto))
        else:
            print_help()
        return
    
    # Interactive mode
    print_welcome()
    
    while True:
        try:
            user = input("\n  > ").strip()
            if not user:
                continue
            cmd = user.lower()
            if cmd in ["quit", "q", "exit"]:
                print("\n  Bye!\n")
                break
            elif cmd == "clear":
                print("\n" * 30)
                print_welcome()
            elif cmd in ["help", "h", "?", "status"]:
                if cmd == "status":
                    show_status()
                else:
                    print_help()
            elif "." in user or user.replace(".", "").replace("-", "").replace("_", "").isalpha():
                asyncio.run(smart_crawl_workflow(user))
                print()
                print("  Done. Enter command...")
        except:
            break


if __name__ == "__main__":
    main()
