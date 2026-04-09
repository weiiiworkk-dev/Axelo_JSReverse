"""
Axelo Interactive Config - Handle user input for API selection and crawl configuration
"""

from dataclasses import dataclass
from axelo.ui.models import (
    APICandidate, 
    CrawlConfig,
    CONTENT_TYPE_MAP,
    CONTENT_TYPE_LABELS,
    SCALE_MAP,
    SPEED_MAP,
    FORMAT_MAP,
    calculate_estimate,
)


def print_header(title: str) -> None:
    """Print section header"""
    print()
    print(f"  {title}")
    print("  " + "-" * 50)


def print_api_list(apis: list[APICandidate]) -> None:
    """
    Print discovered API list
    
    Args:
        apis: List of discovered API candidates
    """
    print_header(f"Discovered {len(apis)} API Interfaces")
    
    if not apis:
        print("  No APIs discovered.")
        return
    
    # Group by resource type
    by_type = {}
    for api in apis:
        rt = api.resource_type or "unknown"
        if rt not in by_type:
            by_type[rt] = []
        by_type[rt].append(api)
    
    # Print by type
    for resource_type, api_list in by_type.items():
        print(f"\n  [{resource_type.upper()}]")
        for api in api_list[:10]:  # Max 10 per type
            conf_pct = int(api.confidence * 100)
            method_color = "G" if api.method == "GET" else "P"  # G=GET, P=POST
            print(f"  [{api.index:2d}] [{method_color}] {api.url[:60]}")
            if len(api.url) > 60:
                print(f"        {api.url[60:]}")
            print(f"        Confidence: {conf_pct}%  |  Signals: {', '.join(api.protection_signals[:3]) or 'none'}")
    
    if len(apis) > 50:
        print(f"\n  ... and {len(apis) - 50} more APIs")


def select_apis(apis: list[APICandidate]) -> list[APICandidate]:
    """
    Prompt user to select APIs
    
    Returns:
        List of selected APICandidate objects
    """
    print("\n  Select APIs to crawl (comma-separated, e.g., 1,3,5):")
    print("  Or press Enter to select the first API, 'a' for all: ")
    
    while True:
        user_input = input("\n  > ").strip().lower()
        
        if not user_input:
            # Default: select first API
            return [apis[0]] if apis else []
        
        if user_input == "a":
            return apis
        
        try:
            # Parse selection
            selected_indices = []
            for part in user_input.split(","):
                part = part.strip()
                if "-" in part:
                    # Range selection (e.g., 1-5)
                    start, end = part.split("-")
                    selected_indices.extend(range(int(start), int(end) + 1))
                else:
                    selected_indices.append(int(part))
            
            # Get selected APIs
            selected = []
            for idx in selected_indices:
                if 0 < idx <= len(apis):
                    selected.append(apis[idx - 1])  # 1-based to 0-based
            
            if selected:
                return selected
            else:
                print("  Invalid selection. Please try again.")
    
        except ValueError:
            print("  Invalid format. Use: 1,2,3 or 1-5")


def select_content_type() -> str:
    """
    Prompt user to select content type
    
    Returns:
        Content type string
    """
    print_header("Select Crawl Content")
    
    options = [
        ("1", "name_only", "Name only"),
        ("2", "name_price", "Name + Price"),
        ("3", "detail", "Product Detail"),
        ("4", "review", "Reviews"),
        ("5", "all", "All Content"),
    ]
    
    for key, value, label in options:
        print(f"  [{key}] {label}")
    
    while True:
        user_input = input("\n  > ").strip()
        if user_input in CONTENT_TYPE_MAP:
            return CONTENT_TYPE_MAP[user_input]
        print("  Invalid selection. Please try again.")


def select_scale() -> tuple[str, int]:
    """
    Prompt user to select crawl scale
    
    Returns:
        Tuple of (scale_name, item_limit)
    """
    print_header("Select Crawl Scale")
    
    options = [
        ("1", "Small", 100),
        ("2", "Medium", 1000),
        ("3", "Large", "all"),
        ("4", "Custom", None),
    ]
    
    for key, label, limit in options:
        limit_str = str(limit) if limit else "all"
        print(f"  [{key}] {label} ({limit_str} items)")
    
    while True:
        user_input = input("\n  > ").strip()
        
        if user_input in SCALE_MAP:
            scale_name, limit = SCALE_MAP[user_input]
            if limit is None:
                # Custom input
                print("  Enter custom limit (1-10000):")
                custom = input("  > ").strip()
                try:
                    limit = int(custom)
                    return "custom", limit
                except ValueError:
                    continue
            return scale_name, limit
        
        if user_input == "4":
            print("  Enter custom limit (1-10000):")
            try:
                limit = int(input("  > ").strip())
                return "custom", limit
            except ValueError:
                continue
        
        print("  Invalid selection. Please try again.")


def select_speed() -> tuple[str, int]:
    """
    Prompt user to select crawl speed
    
    Returns:
        Tuple of (speed_name, requests_per_second)
    """
    print_header("Select Crawl Speed")
    
    options = [
        ("1", "slow", "1 req/s (slow but stable)"),
        ("2", "medium", "5 req/s (balanced)"),
        ("3", "fast", "20 req/s (fast, may trigger anti-bot)"),
    ]
    
    for key, name, desc in options:
        print(f"  [{key}] {name.title()} - {desc}")
    
    while True:
        user_input = input("\n  > ").strip()
        if user_input in SPEED_MAP:
            return SPEED_MAP[user_input]
        print("  Invalid selection. Please try again.")


def select_output_format() -> str:
    """
    Prompt user to select output format
    
    Returns:
        Output format string
    """
    print_header("Select Output Format")
    
    options = [
        ("1", "json", "JSON file"),
        ("2", "csv", "CSV file"),
        ("3", "mysql", "MySQL database"),
        ("4", "print", "Print to console"),
    ]
    
    for key, value, label in options:
        print(f"  [{key}] {label}")
    
    while True:
        user_input = input("\n  > ").strip()
        if user_input in FORMAT_MAP:
            return FORMAT_MAP[user_input]
        print("  Invalid selection. Please try again.")


def configure_crawl(selected_api: APICandidate) -> CrawlConfig:
    """
    Prompt user to configure crawl parameters
    
    Args:
        selected_api: The selected API to crawl
        
    Returns:
        Configured CrawlConfig
    """
    config = CrawlConfig()
    config.selected_apis = [selected_api.url]
    
    # Content type
    config.content_type = select_content_type()
    
    # Scale
    scale_name, limit = select_scale()
    config.item_limit = limit
    
    # Speed
    config.crawl_rate, _ = select_speed()
    
    # Format
    config.output_format = select_output_format()
    
    # Calculate estimate
    config.estimated_cost, config.estimated_duration = calculate_estimate(
        config.item_limit, 
        config.crawl_rate
    )
    
    return config


def print_config_summary(site: str, api: APICandidate, config: CrawlConfig) -> None:
    """
    Print configuration summary for confirmation
    
    Args:
        site: Site name
        api: Selected API
        config: Crawl configuration
    """
    print_header("Confirm Configuration")
    
    print(f"  Target Site:    {site}")
    print(f"  Target API:    {api.url}")
    print(f"  Content:       {CONTENT_TYPE_LABELS.get(config.content_type, config.content_type)}")
    print(f"  Scale:         {config.item_limit} items")
    print(f"  Speed:         {config.crawl_rate} ({config.item_limit / config.estimated_duration:.1f} req/s)")
    print(f"  Format:        {config.output_format.upper()}")
    print(f"  Est. Cost:     ${config.estimated_cost:.2f}")
    print(f"  Est. Duration: {config.estimated_duration:.0f}s")
    print()
    
    # Confirm
    confirm = input("  Confirm? [Y/n]: ").strip().lower()
    
    if confirm not in ["", "y", "yes"]:
        print("\n  Cancelled.")
        return None
    
    return config
