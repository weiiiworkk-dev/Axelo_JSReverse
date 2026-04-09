"""
Axelo Wizard Module (Stub)

Note: This module has been refactored. The old wizard interface has been 
replaced by the new tool-based architecture in axelo/tools/ and axelo/chat/.

This stub provides backward compatibility for code that still references it.
"""
from __future__ import annotations


def _resolve_site(site: str) -> tuple[str, dict]:
    """
    Resolve a site string to a URL and metadata.
    
    Args:
        site: Site string (e.g., 'example.com', 'api.example.org')
        
    Returns:
        Tuple of (url, metadata_dict)
    """
    raw_site = (site or "").strip()
    normalized = raw_site

    if not normalized.startswith(("http://", "https://")):
        # Generic normalization:
        # - if user passes a plain token like "amazon", resolve to "www.amazon.com"
        # - if user passes domain-like input with dot, keep it as is
        if "." not in normalized and normalized:
            normalized = f"www.{normalized}.com"
        url = f"https://{normalized}"
    else:
        url = normalized
    
    metadata = {
        "site": raw_site,
        "resolved": True,
        "method": "normalized"
    }
    
    return url, metadata


def resolve_url(site: str) -> str:
    """Simple URL resolution - returns URL with https:// prefix if missing."""
    url, _ = _resolve_site(site)
    return url


__all__ = ["_resolve_site", "resolve_url"]