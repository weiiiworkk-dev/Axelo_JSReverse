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
        site: Site string (e.g., 'amazon.com', 'jd.com')
        
    Returns:
        Tuple of (url, metadata_dict)
    """
    # Simple URL construction
    if not site.startswith(('http://', 'https://')):
        url = f"https://{site}"
    else:
        url = site
    
    metadata = {
        "site": site,
        "resolved": True,
        "method": "simple"
    }
    
    return url, metadata


def resolve_url(site: str) -> str:
    """Simple URL resolution - returns URL with https:// prefix if missing."""
    url, _ = _resolve_site(site)
    return url


__all__ = ["_resolve_site", "resolve_url"]