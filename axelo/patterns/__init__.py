"""
Patterns Module (DEPRECATED)

This module has been moved to axelo.utils.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.patterns is deprecated. "
    "Use axelo.utils instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .common import SiteProfile, KNOWN_PROFILES, match_profile

__all__ = ["SiteProfile", "KNOWN_PROFILES", "match_profile"]
