"""Adaptive rate controller - Dynamic request rate management."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class DomainHistory:
    """Historical data for a domain."""
    requests: list[float] = field(default_factory=list)
    errors: list[float] = field(default_factory=list)
    response_times: list[float] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        total = len(self.requests)
        if total == 0:
            return 1.0
        return 1 - (len(self.errors) / total)
    
    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 1000
        return sum(self.response_times) / len(self.response_times)
    
    def add(self, response_time: float, is_error: bool = False) -> None:
        now = time.time()
        self.requests.append(now)
        if is_error:
            self.errors.append(now)
        self.response_times.append(response_time)
        
        # Keep only last 100 entries
        if len(self.requests) > 100:
            self.requests = self.requests[-100:]
            self.errors = self.errors[-100:]
            self.response_times = self.response_times[-100:]


@dataclass
class PacingStrategy:
    """Pacing strategy configuration."""
    name: str
    min_interval_ms: float
    max_interval_ms: float
    adaptive_enabled: bool = True
    
    def get_min_interval(self, history: DomainHistory | None = None) -> float:
        """Get minimum interval based on strategy and history."""
        if history is None or not self.adaptive_enabled:
            return self.min_interval_ms
        
        # Adjust based on success rate
        success_rate = history.success_rate if history else 1.0
        
        if success_rate > 0.9:
            return self.min_interval_ms * 0.7
        elif success_rate > 0.7:
            return self.min_interval_ms
        elif success_rate > 0.5:
            return self.min_interval_ms * 1.5
        else:
            return self.max_interval_ms


class PacingModel:
    """Pacing model - Learn optimal request rate from history."""
    
    def __init__(self):
        self._domain_histories: dict[str, DomainHistory] = {}
    
    def update(self, domain: str, response_time: float, is_error: bool = False) -> None:
        """Update history for domain."""
        if domain not in self._domain_histories:
            self._domain_histories[domain] = DomainHistory()
        
        self._domain_histories[domain].add(response_time, is_error)
    
    def get_history(self, domain: str) -> DomainHistory | None:
        """Get history for domain."""
        return self._domain_histories.get(domain)
    
    def get_recommended_interval(self, domain: str) -> float:
        """Get recommended interval in ms."""
        history = self.get_history(domain)
        if not history:
            return 1000
        
        success_rate = history.success_rate
        avg_time = history.avg_response_time
        
        # Calculate base interval
        base = max(500, min(5000, avg_time * 2))
        
        # Adjust based on success rate
        if success_rate > 0.9:
            return base * 0.5
        elif success_rate > 0.7:
            return base
        elif success_rate > 0.5:
            return base * 2
        else:
            return base * 4


class AdaptiveRateController:
    """Adaptive rate controller - Dynamic request rate based on target response."""
    
    # Predefined strategies
    STRATEGIES = {
        "conservative": PacingStrategy(
            name="conservative",
            min_interval_ms=2000,
            max_interval_ms=10000,
        ),
        "moderate": PacingStrategy(
            name="moderate",
            min_interval_ms=1000,
            max_interval_ms=5000,
        ),
        "aggressive": PacingStrategy(
            name="aggressive",
            min_interval_ms=500,
            max_interval_ms=2000,
        ),
    }
    
    def __init__(self, default_strategy: str = "moderate"):
        self._pacing_model = PacingModel()
        self._strategy_selector = StrategySelector()
        self._domain_strategies: dict[str, PacingStrategy] = {}
        self._last_request_time: dict[str, float] = {}
        self._default_strategy = self.STRATEGIES.get(
            default_strategy, 
            self.STRATEGIES["moderate"]
        )
    
    async def acquire(self, domain: str) -> None:
        """Acquire permission to make request (may wait).
        
        Args:
            domain: Target domain
        """
        # Get strategy for domain
        strategy = self._domain_strategies.get(domain, self._default_strategy)
        
        # Get history
        history = self._pacing_model.get_history(domain)
        
        # Calculate interval
        interval = strategy.get_min_interval(history)
        
        # Apply adaptive adjustment
        adaptive_interval = self._calculate_adaptive_delay(domain, interval, history)
        
        # Wait if needed
        last_time = self._last_request_time.get(domain, 0)
        elapsed = (time.time() * 1000) - last_time
        
        if elapsed < adaptive_interval:
            wait_time = (adaptive_interval - elapsed) / 1000
            log.debug("rate_limit_waiting",
                     domain=domain,
                     wait_ms=adaptive_interval - elapsed)
            await asyncio.sleep(wait_time)
        
        # Update last request time
        self._last_request_time[domain] = time.time() * 1000
    
    def _calculate_adaptive_delay(
        self, 
        domain: str, 
        base_delay: float,
        history: DomainHistory | None
    ) -> float:
        """Calculate adaptive delay based on response quality."""
        if history is None or not history.response_times:
            return base_delay
        
        recent_times = history.response_times[-10:]
        recent_errors = [t for t in history.errors[-10:] 
                        if time.time() - t < 60]  # Last 60 seconds
        
        # Calculate error rate
        error_rate = len(recent_errors) / max(1, len(recent_times))
        
        # Calculate response time variance
        if len(recent_times) >= 2:
            avg = sum(recent_times) / len(recent_times)
            variance = sum((t - avg) ** 2 for t in recent_times) / len(recent_times)
            std_dev = variance ** 0.5
            
            # High variance = potential rate limit
            if std_dev > avg * 0.5:
                return base_delay * 2.5
        
        # Adjust based on error rate
        if error_rate > 0.3:
            return base_delay * 4
        elif error_rate > 0.15:
            return base_delay * 2
        elif error_rate > 0.05:
            return base_delay * 1.3
        
        return base_delay
    
    def on_response(
        self, 
        domain: str, 
        response_time: float,
        status_code: int = 200
    ) -> None:
        """Record response to adjust strategy.
        
        Args:
            domain: Target domain
            response_time: Response time in ms
            status_code: HTTP status code
        """
        is_error = status_code >= 400
        
        # Update pacing model
        self._pacing_model.update(domain, response_time, is_error)
        
        # Check if strategy needs adjustment
        history = self._pacing_model.get_history(domain)
        if history:
            new_strategy = self._strategy_selector.select(
                domain, history, self._domain_strategies.get(domain)
            )
            if new_strategy != self._domain_strategies.get(domain):
                self._domain_strategies[domain] = new_strategy
                log.info("strategy_changed",
                        domain=domain,
                        old_strategy=self._domain_strategies.get(domain, self._default_strategy).name,
                        new_strategy=new_strategy.name)
    
    def set_strategy(self, domain: str, strategy_name: str) -> None:
        """Manually set strategy for domain."""
        if strategy_name in self.STRATEGIES:
            self._domain_strategies[domain] = self.STRATEGIES[strategy_name]
    
    def get_current_strategy(self, domain: str) -> str:
        """Get current strategy name for domain."""
        strategy = self._domain_strategies.get(domain, self._default_strategy)
        return strategy.name


class StrategySelector:
    """Select optimal pacing strategy based on history."""
    
    def select(
        self, 
        domain: str, 
        history: DomainHistory,
        current: PacingStrategy | None = None
    ) -> PacingStrategy:
        """Select best strategy."""
        if not history.requests:
            return AdaptiveRateController.STRATEGIES["moderate"]
        
        success_rate = history.success_rate
        recent_errors = len([t for t in history.errors 
                           if time.time() - t < 300])  # Last 5 minutes
        
        # Determine strategy
        if recent_errors > 5 or success_rate < 0.3:
            return AdaptiveRateController.STRATEGIES["conservative"]
        elif recent_errors > 2 or success_rate < 0.6:
            return AdaptiveRateController.STRATEGIES["moderate"]
        elif success_rate > 0.9 and recent_errors == 0:
            return AdaptiveRateController.STRATEGIES["aggressive"]
        else:
            return current or AdaptiveRateController.STRATEGIES["moderate"]


# Convenience function
def create_rate_controller(
    strategy: str = "moderate"
) -> AdaptiveRateController:
    """Create rate controller with specified strategy."""
    return AdaptiveRateController(default_strategy=strategy)