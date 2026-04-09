"""
Axelo UI Data Models - Data models for smart crawl system
"""

from enum import Enum
from typing import Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class TaskMode(Enum):
    """Task execution mode"""
    REVERSE = "reverse"
    CRAWL = "crawl"
    BRIDGE = "bridge"
    REFRESH = "refresh"


class ContentType(Enum):
    """Crawl content type"""
    NAME_ONLY = "name_only"
    NAME_PRICE = "name_price"
    DETAIL = "detail"
    REVIEW = "review"
    ALL = "all"


class CrawlScale(Enum):
    """Crawl scale options"""
    SMALL = "small"      # 100 items
    MEDIUM = "medium"    # 1000 items
    LARGE = "large"     # all
    CUSTOM = "custom"


class CrawlSpeed(Enum):
    """Crawl speed options"""
    SLOW = "slow"       # 1 req/s
    MEDIUM = "medium"   # 5 req/s
    FAST = "fast"       # 20 req/s


class OutputFormat(Enum):
    """Output format"""
    JSON = "json"
    CSV = "csv"
    MYSQL = "mysql"
    PRINT = "print"


class ResourceType(Enum):
    """Discovered API resource type"""
    SEARCH_RESULTS = "search_results"
    PRODUCT_LISTING = "product_listing"
    PRODUCT_DETAIL = "product_detail"
    REVIEWS = "reviews"
    CONTENT_LISTING = "content_listing"
    USER_PROFILE = "user_profile"
    UNKNOWN = "unknown"


class WorkflowState(Enum):
    """Workflow state machine"""
    START = "start"
    SITE_INPUT = "site_input"
    SCAN_API = "scan_api"
    SELECT_API = "select_api"
    CONFIGURE = "configure"
    REVERSE = "reverse"
    CRAWL = "crawl"
    RESULT = "result"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class APICandidate:
    """Discovered API candidate"""
    url: str
    method: str = "GET"
    description: str = ""
    resource_type: str = ""
    confidence: float = 0.0
    protection_signals: list[str] = field(default_factory=list)
    index: int = 0


@dataclass
class CrawlConfig:
    """User crawl configuration"""
    selected_apis: list[str] = field(default_factory=list)
    content_type: str = "name_price"
    item_limit: int = 100
    page_limit: int | None = None
    crawl_rate: str = "medium"
    output_format: str = "json"
    estimated_cost: float = 0.0
    estimated_duration: float = 0.0


@dataclass
class CrawlResult:
    """Crawl execution result"""
    total: int = 0
    success: int = 0
    failed: int = 0
    duration: float = 0.0
    cost: float = 0.0
    output_path: str = ""
    status: str = "pending"


@dataclass
class AxeloRequest:
    """Complete request"""
    site: str = ""
    url: str = ""
    discovered_apis: list[APICandidate] = field(default_factory=list)
    selected_api: str = ""
    config: CrawlConfig = field(default_factory=CrawlConfig)
    session_id: str = ""
    state: str = "start"
    result: CrawlResult = field(default_factory=CrawlResult)


# Pydantic models for config validation
class CrawlConfigModel(BaseModel):
    """Validated crawl configuration"""
    content_type: str = "name_price"
    item_limit: int = Field(default=100, ge=1, le=10000)
    page_limit: int | None = Field(default=None, ge=1)
    crawl_rate: str = "medium"
    output_format: str = "json"


# Mapping from user-friendly to internal
CONTENT_TYPE_MAP = {
    "1": "name_only",
    "2": "name_price", 
    "3": "detail",
    "4": "review",
    "5": "all",
}

CONTENT_TYPE_LABELS = {
    "name_only": "Name only",
    "name_price": "Name + Price",
    "detail": "Product Detail",
    "review": "Reviews",
    "all": "All Content",
}

SCALE_MAP = {
    "1": ("small", 100),
    "2": ("medium", 1000),
    "3": ("large", None),  # None means all
}

SPEED_MAP = {
    "1": ("slow", 1),
    "2": ("medium", 5),
    "3": ("fast", 20),
}

FORMAT_MAP = {
    "1": "json",
    "2": "csv",
    "3": "mysql",
    "4": "print",
}


def infer_resource_type(url: str, description: str = "") -> str:
    """Infer resource type from URL and description"""
    url_lower = url.lower()
    desc_lower = description.lower()
    
    if any(kw in url_lower or kw in desc_lower for kw in ["search", "/s?", "keyword", "query"]):
        return "search_results"
    if any(kw in url_lower or kw in desc_lower for kw in ["product", "item", "detail", "/p/"]):
        return "product_listing"
    if any(kw in url_lower or kw in desc_lower for kw in ["review", "comment"]):
        return "reviews"
    if any(kw in url_lower or kw in desc_lower for kw in ["video", "content", "feed"]):
        return "content_listing"
    if any(kw in url_lower or kw in desc_lower for kw in ["user", "profile", "account"]):
        return "user_profile"
    
    return "unknown"


def calculate_estimate(item_limit: int, crawl_rate: str) -> tuple[float, float]:
    """Calculate estimated cost and duration"""
    rates = {"slow": 1, "medium": 5, "fast": 20}
    rate = rates.get(crawl_rate, 5)
    
    # Assume ~0.001 USD per request (reverse cost already paid)
    cost_per_item = 0.001
    cost = item_limit * cost_per_item
    
    # Duration in seconds
    duration = item_limit / rate
    
    return cost, duration
