from .action_runner import ActionRunner, ActionRunResult, default_action_flow
from .bridge_client import BridgeClient, BridgeDriver
from .challenge_monitor import ChallengeMonitor, ChallengeState
from .cookie_lifetime_estimator import CookieLifetimeEstimator
from .cookie_pool import CookieJar, CookiePoolCoordinator
from .driver import BrowserDriver
from .headful_escalator import HeadfulEscalator
from .hooks import DEFAULT_HOOK_TARGETS, JSHookInjector
from .interceptor import NetworkInterceptor
from .js_challenge_solver import JSChallengeSolver
from .profile_pool import BrowserProfilePool
from .real_browser_resolver import RealBrowserResolver, ResolvedSession
from .session_pool import SessionPool
from .state_store import BrowserStateStore
from .unified import PoolManager, SessionPool as UnifiedSessionPool
# Network exports
from axelo.network import ProxyConfig, ProxyManager, RequestPacingModel

# Enhanced modules (optional - graceful fallback)
try:
    from .enhanced_driver import EnhancedBrowserDriver, create_enhanced_driver
except ImportError:
    EnhancedBrowserDriver = None
    create_enhanced_driver = None

__all__ = [
    "ActionRunResult",
    "ActionRunner",
    "BridgeClient",
    "BridgeDriver",
    "BrowserDriver",
    "BrowserProfilePool",
    "BrowserStateStore",
    "ChallengeMonitor",
    "ChallengeState",
    "CookieJar",
    "CookieLifetimeEstimator",
    "CookiePoolCoordinator",
    "DEFAULT_HOOK_TARGETS",
    "HeadfulEscalator",
    "JSChallengeSolver",
    "JSHookInjector",
    "NetworkInterceptor",
    "PoolManager",
    "ProxyConfig",
    "ProxyManager",
    "RequestPacingModel",
    "RealBrowserResolver",
    "ResolvedSession",
    "SessionPool",
    "UnifiedSessionPool",
    "default_action_flow",
]

# Add enhanced modules if available
if EnhancedBrowserDriver:
    __all__.extend(["EnhancedBrowserDriver", "create_enhanced_driver"])
