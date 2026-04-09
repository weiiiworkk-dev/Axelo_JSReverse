"""
Network Module (DEPRECATED)

This module has been moved to axelo.browser.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

warnings.warn(
    "axelo.network is deprecated. "
    "Use axelo.browser instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep original exports for backward compatibility
from .proxy_manager import ProxyConfig, ProxyManager
from .pacing_model import RequestPacingModel

__all__ = ["ProxyConfig", "ProxyManager", "RequestPacingModel"]
