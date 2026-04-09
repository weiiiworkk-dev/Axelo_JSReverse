"""
Adaptive Learning System

Learns from success and failure to continuously improve the reverse engine.
This is the key component for making the system self-improving.

Version: 1.0
Created: 2026-04-07
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from collections import defaultdict
from datetime import datetime

import structlog

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SuccessPattern:
    """A successful pattern learned"""
    id: str
    domain_pattern: str  # e.g., "*.example.com"
    algorithm: str
    key_source: str
    parameter_order: list[str]
    success_count: int = 1
    last_success: float = field(default_factory=time.time)
    confidence_boost: float = 0.0


@dataclass
class FailurePattern:
    """A failure pattern learned"""
    id: str
    domain_pattern: str
    error_type: str  # timeout, auth_error, etc.
    attempted_algorithm: str
    failure_count: int = 1
    last_failure: float = field(default_factory=time.time)
    recovery_suggestions: list[str] = field(default_factory=list)


@dataclass
class AdaptiveHint:
    """Hint for improving inference based on learning"""
    source: str  # "success_pattern", "failure_recovery"
    domain_pattern: str
    hint_type: str  # "algorithm", "key_source", "parameter_order"
    value: Any
    confidence: float


# =============================================================================
# PATTERN DATABASE
# =============================================================================

class PatternDatabase:
    """
    Database for storing learned patterns
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("data/adaptive_patterns.json")
        self.success_patterns: dict[str, SuccessPattern] = {}
        self.failure_patterns: dict[str, FailurePattern] = {}
        self._load()
    
    def _load(self):
        """Load patterns from file"""
        if self.db_path.exists():
            try:
                with open(self.db_path, "r") as f:
                    data = json.load(f)
                    
                for p in data.get("success", []):
                    self.success_patterns[p["id"]] = SuccessPattern(**p)
                    
                for p in data.get("failure", []):
                    self.failure_patterns[p["id"]] = FailurePattern(**p)
                    
                log.info("patterns_loaded", 
                         success=len(self.success_patterns),
                         failure=len(self.failure_patterns))
            except Exception as e:
                log.warning("pattern_load_failed", error=str(e))
    
    def save(self):
        """Save patterns to file"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "success": [vars(p) for p in self.success_patterns.values()],
            "failure": [vars(p) for p in self.failure_patterns.values()],
            "updated_at": time.time(),
        }
        
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def add_success(self, pattern: SuccessPattern):
        """Add a success pattern"""
        if pattern.id in self.success_patterns:
            existing = self.success_patterns[pattern.id]
            existing.success_count += 1
            existing.last_success = time.time()
        else:
            self.success_patterns[pattern.id] = pattern
    
    def add_failure(self, pattern: FailurePattern):
        """Add a failure pattern"""
        if pattern.id in self.failure_patterns:
            existing = self.failure_patterns[pattern.id]
            existing.failure_count += 1
            existing.last_failure = time.time()
        else:
            self.failure_patterns[pattern.id] = pattern
    
    def get_success_hints(self, domain: str) -> list[AdaptiveHint]:
        """Get success-based hints for a domain"""
        hints = []
        
        for pattern in self.success_patterns.values():
            if self._match_domain(domain, pattern.domain_pattern):
                hints.append(AdaptiveHint(
                    source="success_pattern",
                    domain_pattern=pattern.domain_pattern,
                    hint_type="algorithm",
                    value=pattern.algorithm,
                    confidence=min(pattern.success_count * 0.1, 0.9),
                ))
                
                if pattern.key_source:
                    hints.append(AdaptiveHint(
                        source="success_pattern",
                        domain_pattern=pattern.domain_pattern,
                        hint_type="key_source",
                        value=pattern.key_source,
                        confidence=min(pattern.success_count * 0.1, 0.9),
                    ))
        
        return hints
    
    def get_failure_hints(self, domain: str, error_type: str) -> list[AdaptiveHint]:
        """Get failure-based hints for a domain and error"""
        hints = []
        
        for pattern in self.failure_patterns.values():
            if (self._match_domain(domain, pattern.domain_pattern) and 
                pattern.error_type == error_type):
                
                for suggestion in pattern.recovery_suggestions:
                    hints.append(AdaptiveHint(
                        source="failure_recovery",
                        domain_pattern=pattern.domain_pattern,
                        hint_type="recovery",
                        value=suggestion,
                        confidence=min(pattern.failure_count * 0.1, 0.8),
                    ))
        
        return hints
    
    def _match_domain(self, domain: str, pattern: str) -> bool:
        """Check if domain matches pattern"""
        import re
        
        # Convert wildcard pattern to regex
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
        return bool(re.match(f"^{regex_pattern}$", domain))


# =============================================================================
# ADAPTIVE LEARNER
# =============================================================================

class AdaptiveLearner:
    """
    Adaptive Learning System
    
    Learns from each reverse operation to improve future results.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db = PatternDatabase(db_path)
        self._stats = {
            "total_inferences": 0,
            "successful_inferences": 0,
            "failed_inferences": 0,
            "accuracy_rate": 0.0,
        }
    
    def on_success(
        self,
        domain: str,
        hypothesis: dict,
        confidence: float,
    ):
        """
        Record a successful inference
        
        Args:
            domain: Target domain
            hypothesis: Signature hypothesis
            confidence: Confidence score
        """
        log.info("learning_success", domain=domain, confidence=confidence)
        
        # Create pattern
        pattern = SuccessPattern(
            id=f"{domain}_{hypothesis.get('algorithm', 'unknown')}",
            domain_pattern=f"*.{domain.split('.')[-2:]}.*",
            algorithm=hypothesis.get("algorithm", "unknown"),
            key_source=hypothesis.get("key_source", "unknown"),
            parameter_order=hypothesis.get("parameter_order", []),
            confidence_boost=confidence - 0.5,  # Boost if confident
        )
        
        self.db.add_success(pattern)
        self.db.save()
        
        # Update stats
        self._stats["successful_inferences"] += 1
        self._update_accuracy_rate()
    
    def on_failure(
        self,
        domain: str,
        error_type: str,
        attempted_algorithm: str,
        recovery_actions: list[str],
    ):
        """
        Record a failed inference
        
        Args:
            domain: Target domain
            error_type: Type of error
            attempted_algorithm: Algorithm that was attempted
            recovery_actions: Actions that might help
        """
        log.info("learning_failure", domain=domain, error=error_type)
        
        # Create pattern
        pattern = FailurePattern(
            id=f"{domain}_{error_type}",
            domain_pattern=f"*.{domain.split('.')[-2:]}.*",
            error_type=error_type,
            attempted_algorithm=attempted_algorithm,
            recovery_suggestions=recovery_actions,
        )
        
        self.db.add_failure(pattern)
        self.db.save()
        
        # Update stats
        self._stats["failed_inferences"] += 1
        self._update_accuracy_rate()
    
    def get_hints(self, domain: str) -> dict:
        """
        Get adaptive hints for a domain
        
        Args:
            domain: Target domain
            
        Returns:
            Dictionary of hints
        """
        success_hints = self.db.get_success_hints(domain)
        failure_hints = self.db.get_failure_hints(domain, "timeout")  # Common error
        auth_hints = self.db.get_failure_hints(domain, "auth_error")
        
        hints = {
            "algorithm": [],
            "key_source": [],
            "parameter_order": [],
            "recovery": [],
        }
        
        for hint in success_hints:
            if hint.hint_type == "algorithm":
                hints["algorithm"].append({"value": hint.value, "confidence": hint.confidence})
            elif hint.hint_type == "key_source":
                hints["key_source"].append({"value": hint.value, "confidence": hint.confidence})
        
        for hint in failure_hints + auth_hints:
            hints["recovery"].append({"value": hint.value, "confidence": hint.confidence})
        
        return hints
    
    def _update_accuracy_rate(self):
        """Update accuracy rate"""
        total = self._stats["successful_inferences"] + self._stats["failed_inferences"]
        if total > 0:
            self._stats["accuracy_rate"] = (
                self._stats["successful_inferences"] / total
            )
    
    def get_stats(self) -> dict:
        """Get learning statistics"""
        return dict(self._stats)


# =============================================================================
# INTEGRATION WITH ENGINE
# =============================================================================

class AdaptiveInferenceEngine:
    """
    Wraps the signature engine with adaptive learning
    """
    
    def __init__(self, signature_engine, db_path: Optional[Path] = None):
        self._engine = signature_engine
        self._learner = AdaptiveLearner(db_path)
    
    async def infer(
        self,
        traffic,
        enable_learning: bool = True,
    ) -> dict:
        """
        Infer with adaptive learning
        
        Args:
            traffic: Standard traffic
            enable_learning: Whether to learn from this inference
        """
        # Get hints from learning
        hints = {}
        if enable_learning:
            hints = self._learner.get_hints(traffic.domain)
        
        # Run inference (with hints passed to engine if supported)
        result = await self._engine.infer(traffic)
        
        # Record success/failure (typically after verification)
        # This would be called externally after verification
        
        return {
            "result": result,
            "hints": hints,
            "learned_from_previous": len(hints.get("algorithm", [])) > 0,
        }
    
    def record_success(self, domain: str, hypothesis: dict, confidence: float):
        """Record a successful inference"""
        self._learner.on_success(domain, hypothesis, confidence)
    
    def record_failure(
        self,
        domain: str,
        error_type: str,
        algorithm: str,
        recovery: list[str],
    ):
        """Record a failed inference"""
        self._learner.on_failure(domain, error_type, algorithm, recovery)
    
    def get_stats(self) -> dict:
        """Get learning statistics"""
        return self._learner.get_stats()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SuccessPattern",
    "FailurePattern", 
    "AdaptiveHint",
    "PatternDatabase",
    "AdaptiveLearner",
    "AdaptiveInferenceEngine",
]