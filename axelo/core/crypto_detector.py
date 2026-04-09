"""
Universal Crypto Detector (DEPRECATED)

This module has been moved to axelo.analysis.crypto.
Please update your imports:

    from axelo.analysis.crypto import UniversalCryptoDetector

This file is kept for backward compatibility and will be removed in a future version.

Version: 1.1 (Deprecated)
Created: 2026-04-07
"""

import warnings

# Re-export from new location for backward compatibility
from axelo.analysis.crypto import (
    CryptoType,
    CryptoAlgorithm,
    CryptoOperation,
    KeySource,
    CryptoAnalysis,
    UniversalCryptoDetector,
    detect_crypto,
)

warnings.warn(
    "axelo.core.crypto_detector is deprecated. "
    "Use axelo.analysis.crypto instead.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    "CryptoType",
    "CryptoAlgorithm", 
    "CryptoOperation",
    "KeySource",
    "CryptoAnalysis",
    "UniversalCryptoDetector",
    "detect_crypto",
]