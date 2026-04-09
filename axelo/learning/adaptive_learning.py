"""Adaptive learning system - Continuous learning from success and failure."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class RequestContext:
    """Context of a request."""
    domain: str
    url: str
    method: str
    headers: dict
    timestamp: float
    strategy_snapshot: dict | None = None
    fingerprint_snapshot: dict | None = None


@dataclass
class RequestResult:
    """Result of a request."""
    success: bool
    status_code: int
    response_time: float
    error: str | None = None
    metrics: dict | None = None


@dataclass
class SuccessPattern:
    """Pattern from successful requests."""
    domain: str
    timestamp: float
    strategy: dict
    response_metrics: dict
    fingerprint: dict
    
    @property
    def confidence(self) -> float:
        # Higher confidence for recent patterns
        age_hours = (time.time() - self.timestamp) / 3600
        return max(0.3, 1.0 - (age_hours / 24))


@dataclass
class FailurePattern:
    """Pattern from failed requests."""
    domain: str
    timestamp: float
    failure_type: str
    error_details: str
    context_snapshot: dict


@dataclass
class StrategySuggestion:
    """Suggestion for strategy."""
    source: str
    confidence: float
    recommendations: dict


@dataclass
class FailureWarning:
    """Warning from failure pattern."""
    failure_type: str
    severity: str
    prevention: str


class PatternIndex:
    """Index for fast pattern lookup."""
    
    def __init__(self):
        self._patterns: list[SuccessPattern] = []
        self._domain_index: dict[str, list[int]] = {}
    
    def add(self, pattern: SuccessPattern) -> None:
        idx = len(self._patterns)
        self._patterns.append(pattern)
        
        if pattern.domain not in self._domain_index:
            self._domain_index[pattern.domain] = []
        self._domain_index[pattern.domain].append(idx)
    
    def find_similar(
        self, 
        context: RequestContext, 
        limit: int = 5
    ) -> list[SuccessPattern]:
        """Find similar patterns."""
        domain_patterns = self._domain_index.get(context.domain, [])
        
        if not domain_patterns:
            return []
        
        # Return most recent patterns
        patterns = [self._patterns[i] for i in domain_patterns]
        patterns.sort(key=lambda p: p.timestamp, reverse=True)
        
        return patterns[:limit]


class SuccessPatternDatabase:
    """Database of success patterns."""
    
    def __init__(self):
        self._patterns: list[SuccessPattern] = []
        self._index = PatternIndex()
        self._max_patterns = 1000
    
    async def record(
        self, 
        context: RequestContext, 
        result: RequestResult
    ) -> None:
        """Record a success pattern."""
        if not result.success:
            return
        
        pattern = SuccessPattern(
            domain=context.domain,
            timestamp=time.time(),
            strategy=context.strategy_snapshot or {},
            response_metrics=result.metrics or {},
            fingerprint=context.fingerprint_snapshot or {},
        )
        
        self._patterns.append(pattern)
        self._index.add(pattern)
        
        # Cleanup old patterns
        if len(self._patterns) > self._max_patterns:
            self._patterns = self._patterns[-self._max_patterns:]
        
        log.debug("success_pattern_recorded",
                 domain=context.domain,
                 total=len(self._patterns))
    
    def get_suggestions(
        self, 
        context: RequestContext
    ) -> list[StrategySuggestion]:
        """Get strategy suggestions."""
        similar = self._index.find_similar(context, limit=5)
        
        if not similar:
            return []
        
        suggestions = []
        for pattern in similar:
            suggestions.append(StrategySuggestion(
                source="success_pattern",
                confidence=pattern.confidence,
                recommendations=self._extract_recommendations(pattern),
            ))
        
        return suggestions
    
    def _extract_recommendations(self, pattern: SuccessPattern) -> dict:
        """Extract actionable recommendations."""
        return {
            "request_interval": pattern.response_metrics.get("avg_interval", 1000),
            "user_agent": pattern.strategy.get("user_agent", ""),
            "proxy_rotation": pattern.strategy.get("proxy_rotation", ""),
            "cookie_refresh": pattern.strategy.get("cookie_refresh", 0),
            "behavior_timing": pattern.strategy.get("behavior_timing", {}),
        }
    
    def get_domain_stats(self, domain: str) -> dict:
        """Get statistics for domain."""
        domain_patterns = [p for p in self._patterns if p.domain == domain]
        
        if not domain_patterns:
            return {"count": 0}
        
        return {
            "count": len(domain_patterns),
            "latest": max(p.timestamp for p in domain_patterns),
            "avg_interval": sum(
                p.response_metrics.get("avg_interval", 0) 
                for p in domain_patterns
            ) / len(domain_patterns),
        }


class FailureClassifier:
    """Classify failure types."""
    
    CLASSIFICATIONS = [
        (r"signature.*expired", "signature_expired"),
        (r"token.*invalid", "token_invalid"),
        (r"cookie.*invalid", "cookie_invalid"),
        (r"rate.*limit|too.*many.*request", "rate_limit"),
        (r"captcha|verify.*human", "captcha"),
        (r"access.*denied|forbidden|403", "access_denied"),
        (r"proxy.*block|ip.*block", "proxy_blocked"),
        (r"timeout", "timeout"),
        (r"connection.*error", "connection_error"),
    ]
    
    def classify(self, error: str | None) -> dict:
        """Classify error."""
        if not error:
            return {"type": "unknown", "confidence": 0}
        
        error_lower = error.lower()
        
        for pattern, failure_type in self.CLASSIFICATIONS:
            import re
            if re.search(pattern, error_lower):
                return {"type": failure_type, "confidence": 0.9}
        
        return {"type": "unknown", "confidence": 0}


class FailurePatternDatabase:
    """Database of failure patterns."""
    
    def __init__(self):
        self._patterns: list[FailurePattern] = []
        self._classifier = FailureClassifier()
        self._max_patterns = 500
    
    async def record(
        self, 
        context: RequestContext, 
        result: RequestResult
    ) -> None:
        """Record a failure pattern."""
        if result.success:
            return
        
        classification = self._classifier.classify(result.error)
        
        pattern = FailurePattern(
            domain=context.domain,
            timestamp=time.time(),
            failure_type=classification["type"],
            error_details=result.error or "",
            context_snapshot={
                "url": context.url,
                "method": context.method,
                "strategy": context.strategy_snapshot or {},
            },
        )
        
        self._patterns.append(pattern)
        
        # Cleanup old patterns
        if len(self._patterns) > self._max_patterns:
            self._patterns = self._patterns[-self._max_patterns:]
        
        log.debug("failure_pattern_recorded",
                 domain=context.domain,
                 failure_type=classification["type"])
    
    def get_warnings(self, context: RequestContext) -> list[FailureWarning]:
        """Get warnings for context."""
        # Get recent failures for domain
        recent_failures = [
            p for p in self._patterns
            if p.domain == context.domain
            and time.time() - p.timestamp < 86400 * 7  # 7 days
        ]
        
        if not recent_failures:
            return []
        
        # Group by failure type
        failure_types: dict[str, list[FailurePattern]] = {}
        for f in recent_failures:
            if f.failure_type not in failure_types:
                failure_types[f.failure_type] = []
            failure_types[f.failure_type].append(f)
        
        warnings = []
        for failure_type, patterns in failure_types.items():
            warnings.append(FailureWarning(
                failure_type=failure_type,
                severity=self._estimate_severity(failure_type, len(patterns)),
                prevention=self._get_prevention(failure_type),
            ))
        
        return warnings
    
    def _estimate_severity(self, failure_type: str, count: int) -> str:
        """Estimate severity based on failure type and count."""
        if count > 10:
            return "high"
        elif count > 3:
            return "medium"
        else:
            return "low"
    
    def _get_prevention(self, failure_type: str) -> str:
        """Get prevention advice."""
        prevention_map = {
            "signature_expired": "增加cookie刷新频率",
            "token_invalid": "重新获取token",
            "cookie_invalid": "刷新session cookie",
            "rate_limit": "降低请求频率",
            "captcha": "使用更慢的操作节奏",
            "proxy_blocked": "更换代理池",
            "access_denied": "检查认证状态",
            "timeout": "增加超时时间",
            "connection_error": "检查网络连接",
        }
        
        return prevention_map.get(failure_type, "检查请求参数")


class StrategyOptimizer:
    """Optimize strategy based on patterns."""
    
    def __init__(self):
        self._domain_strategies: dict[str, dict] = {}
    
    async def update(
        self, 
        context: RequestContext, 
        result: RequestResult
    ) -> None:
        """Update strategy based on result."""
        if context.domain not in self._domain_strategies:
            self._domain_strategies[context.domain] = {}
        
        strategy = self._domain_strategies[context.domain]
        
        if result.success:
            # Record successful strategy
            if "success_count" not in strategy:
                strategy["success_count"] = 0
            strategy["success_count"] += 1
            strategy["last_success"] = time.time()
        else:
            # Record failure
            if "failure_count" not in strategy:
                strategy["failure_count"] = 0
            strategy["failure_count"] += 1
            strategy["last_failure"] = time.time()
    
    def optimize(
        self,
        success_suggestions: list[StrategySuggestion],
        failure_warnings: list[FailureWarning],
        prediction: dict | None = None
    ) -> dict:
        """Optimize strategy based on all inputs."""
        optimized = {
            "adjustments": [],
            "warnings": [],
            "confidence": 0.5,
        }
        
        # Apply success suggestions
        for suggestion in success_suggestions:
            if suggestion.confidence > 0.7:
                for key, value in suggestion.recommendations.items():
                    optimized["adjustments"].append({
                        "type": key,
                        "value": value,
                        "source": "success_pattern",
                    })
                optimized["confidence"] = max(
                    optimized["confidence"], 
                    suggestion.confidence
                )
        
        # Add failure warnings
        for warning in failure_warnings:
            if warning.severity in ("high", "medium"):
                optimized["warnings"].append({
                    "type": warning.failure_type,
                    "prevention": warning.prevention,
                    "severity": warning.severity,
                })
        
        return optimized


class PredictionModel:
    """Predict failure probability."""
    
    def __init__(self):
        self._domain_features: dict[str, dict] = {}
    
    async def update(
        self, 
        context: RequestContext, 
        result: RequestResult
    ) -> None:
        """Update model with new data."""
        if context.domain not in self._domain_features:
            self._domain_features[context.domain] = {
                "success_count": 0,
                "failure_count": 0,
                "recent_success_rate": 1.0,
                "avg_response_time": 0,
            }
        
        features = self._domain_features[context.domain]
        
        if result.success:
            features["success_count"] += 1
        else:
            features["failure_count"] += 1
        
        # Calculate recent success rate (last 20 requests)
        total = features["success_count"] + features["failure_count"]
        if total > 0:
            features["recent_success_rate"] = (
                features["success_count"] / total
            )
        
        # Update avg response time
        if result.response_time > 0:
            n = total - 1
            if n > 0:
                features["avg_response_time"] = (
                    (features["avg_response_time"] * n + result.response_time) / total
                )
    
    def predict(self, context: RequestContext) -> dict:
        """Predict failure probability."""
        features = self._domain_features.get(context.domain)
        
        if not features:
            return {"probability": 0, "confidence": 0}
        
        # Calculate failure probability
        success_rate = features["recent_success_rate"]
        
        # Base probability from success rate
        failure_prob = 1.0 - success_rate
        
        # Adjust for response time
        avg_time = features["avg_response_time"]
        if avg_time > 5000:  # Very slow
            failure_prob += 0.1
        elif avg_time > 2000:  # Slow
            failure_prob += 0.05
        
        return {
            "probability": min(1.0, max(0, failure_prob)),
            "confidence": min(1.0, (features["success_count"] + features["failure_count"]) / 20),
            "success_rate": success_rate,
            "avg_response_time": avg_time,
        }


class AdaptiveLearningSystem:
    """Adaptive learning system - Continuous learning."""
    
    def __init__(self):
        self.success_patterns = SuccessPatternDatabase()
        self.failure_patterns = FailurePatternDatabase()
        self.strategy_optimizer = StrategyOptimizer()
        self.prediction_model = PredictionModel()
    
    async def learn_from_result(
        self, 
        context: RequestContext,
        result: RequestResult
    ) -> None:
        """Learn from request result."""
        if result.success:
            await self.success_patterns.record(context, result)
        else:
            await self.failure_patterns.record(context, result)
        
        await self.strategy_optimizer.update(context, result)
        await self.prediction_model.update(context, result)
    
    def get_optimized_strategy(self, context: RequestContext) -> dict:
        """Get optimized strategy for context."""
        success_suggestions = self.success_patterns.get_suggestions(context)
        failure_warnings = self.failure_patterns.get_warnings(context)
        prediction = self.prediction_model.predict(context)
        
        strategy = self.strategy_optimizer.optimize(
            success_suggestions=success_suggestions,
            failure_warnings=failure_warnings,
            prediction=prediction,
        )
        
        # Add prediction to strategy
        strategy["prediction"] = prediction
        
        return strategy
    
    def get_domain_status(self, domain: str) -> dict:
        """Get learning status for domain."""
        success_stats = self.success_patterns.get_domain_stats(domain)
        
        return {
            "success_patterns": success_stats.get("count", 0),
            "recent_failures": len([
                p for p in self.failure_patterns._patterns
                if p.domain == domain and time.time() - p.timestamp < 86400
            ]),
            "prediction": self.prediction_model.predict(
                RequestContext(domain=domain, url="", method="", headers={}, timestamp=0)
            ),
        }


def create_learning_system() -> AdaptiveLearningSystem:
    """Create learning system instance."""
    return AdaptiveLearningSystem()