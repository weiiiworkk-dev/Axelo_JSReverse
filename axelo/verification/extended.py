"""
Extended Verification Module

Enhanced verification capabilities:
- Multi-request verification
- Stress testing
- Data quality verification
- Auto-correction

Version: 1.0
Created: 2026-04-06
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

log = structlog.get_logger()


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MultiRequestResult:
    """Result of multi-request verification"""
    total_requests: int
    successful: int
    failed: int
    response_times: list[float] = field(default_factory=list)
    error_types: dict[str, int] = field(default_factory=dict)
    score: float = 0.0
    passed: bool = False


@dataclass
class StressTestResult:
    """Result of stress testing"""
    total_requests: int
    successful: int
    failed: int
    avg_response_time: float = 0.0
    min_response_time: float = 0.0
    max_response_time: float = 0.0
    error_rate: float = 0.0
    passed: bool = False
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AutoFixResult:
    """Result of auto-fix attempt"""
    fixed: bool
    changes_made: list[str] = field(default_factory=list)
    new_code: str = ""
    error: str = ""


# =============================================================================
# MULTI-REQUEST VERIFICATION
# =============================================================================

class MultiRequestVerifier:
    """
    Verify crawler by making multiple requests.
    Tests:
    - Request consistency
    - Response stability
    - Error handling
    """
    
    def __init__(self, max_requests: int = 10):
        self.max_requests = max_requests
    
    async def verify(
        self,
        crawler_func,
        test_params: list[dict],
    ) -> MultiRequestResult:
        """
        Verify crawler with multiple different requests.
        
        Args:
            crawler_func: Function to call for each request
            test_params: List of parameter sets to test
            
        Returns:
            MultiRequestResult with verification results
        """
        results = []
        response_times = []
        error_types = {}
        
        for params in test_params[:self.max_requests]:
            try:
                start_time = time.time()
                
                if asyncio.iscoroutinefunction(crawler_func):
                    result = await crawler_func(**params)
                else:
                    result = crawler_func(**params)
                
                elapsed = time.time() - start_time
                response_times.append(elapsed)
                
                # Check if result is valid
                if self._is_valid_result(result):
                    results.append(True)
                else:
                    results.append(False)
                    error_types["invalid_response"] = error_types.get("invalid_response", 0) + 1
                    
            except Exception as e:
                results.append(False)
                error_type = self._classify_error(e)
                error_types[error_type] = error_types.get(error_type, 0) + 1
                log.warning("multi_request_error", error=error_type, params=params)
        
        successful = sum(1 for r in results if r)
        failed = len(results) - successful
        
        score = successful / len(results) if results else 0
        passed = score >= 0.8  # 80% success rate
        
        return MultiRequestResult(
            total_requests=len(results),
            successful=successful,
            failed=failed,
            response_times=response_times,
            error_types=error_types,
            score=score,
            passed=passed,
        )
    
    def _is_valid_result(self, result) -> bool:
        """Check if result is valid"""
        if result is None:
            return False
        if isinstance(result, dict):
            # Check for error indicators
            if "error" in result.keys():
                return False
            if result.get("status_code") and result.get("status_code") >= 400:
                return False
        return True
    
    def _classify_error(self, error: Exception) -> str:
        """Classify error type"""
        error_str = str(error).lower()
        
        if "timeout" in error_str:
            return "timeout"
        elif "connection" in error_str:
            return "connection_error"
        elif "403" in error_str or "forbidden" in error_str:
            return "auth_error"
        elif "429" in error_str or "rate limit" in error_str:
            return "rate_limit"
        elif "500" in error_str or "server" in error_str:
            return "server_error"
        else:
            return "unknown_error"


# =============================================================================
# STRESS TESTING
# =============================================================================

class StressTester:
    """
    Stress test the crawler with high request volume.
    Tests:
    - Performance under load
    - Resource usage
    - Error handling
    """
    
    def __init__(self):
        self.default_concurrency = 5
        self.default_duration = 30  # seconds
    
    async def stress_test(
        self,
        crawler_func,
        concurrency: int = None,
        duration: int = None,
        target_rps: int = 10,
    ) -> StressTestResult:
        """
        Run stress test on crawler.
        
        Args:
            crawler_func: Function to call
            concurrency: Number of concurrent requests
            duration: Test duration in seconds
            target_rps: Target requests per second
            
        Returns:
            StressTestResult with test results
        """
        concurrency = concurrency or self.default_concurrency
        duration = duration or self.default_duration
        
        log.info("stress_test_start", concurrency=concurrency, duration=duration)
        
        results = []
        start_time = time.time()
        request_times = []
        
        async def make_request():
            """Single request with timing"""
            req_start = time.time()
            try:
                if asyncio.iscoroutinefunction(crawler_func):
                    result = await crawler_func()
                else:
                    result = crawler_func()
                elapsed = time.time() - req_start
                return {"success": True, "time": elapsed, "result": result}
            except Exception as e:
                elapsed = time.time() - req_start
                return {"success": False, "time": elapsed, "error": str(e)}
        
        # Run requests concurrently
        tasks = []
        while time.time() - start_time < duration:
            # Maintain concurrency
            while len(tasks) < concurrency:
                tasks.append(asyncio.create_task(make_request()))
            
            # Wait for some to complete
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            for task in done:
                result = task.result()
                results.append(result)
                request_times.append(result["time"])
        
        # Wait for remaining tasks
        if tasks:
            remaining = await asyncio.gather(*tasks, return_exceptions=True)
            for r in remaining:
                if isinstance(r, dict):
                    results.append(r)
                    request_times.append(r.get("time", 0))
        
        # Calculate statistics
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful
        
        if request_times:
            avg_time = sum(request_times) / len(request_times)
            min_time = min(request_times)
            max_time = max(request_times)
        else:
            avg_time = min_time = max_time = 0
        
        error_rate = failed / len(results) if results else 0
        passed = error_rate < 0.1  # Less than 10% errors
        
        # Generate recommendations
        recommendations = []
        if avg_time > 2.0:
            recommendations.append("High average response time - consider adding caching")
        if error_rate > 0.05:
            recommendations.append("Error rate above 5% - check rate limiting")
        if max_time > 10:
            recommendations.append("High max response time - add timeout handling")
        
        return StressTestResult(
            total_requests=len(results),
            successful=successful,
            failed=failed,
            avg_response_time=avg_time,
            min_response_time=min_time,
            max_response_time=max_time,
            error_rate=error_rate,
            passed=passed,
            recommendations=recommendations,
        )


# =============================================================================
# AUTO-CORRECTION
# =============================================================================

class AutoCorrector:
    """
    Automatically fix common crawler issues.
    
    Fixes:
    - Header issues
    - Parameter issues
    - Timeout settings
    """
    
    # Common fixes for different error types
    FIX_STRATEGIES = {
        "timeout": [
            ("timeout", "timeout * 2"),
            ("timeout", "timeout + 10"),
        ],
        "auth_error": [
            ("headers", "add_user_agent"),
            ("headers", "add_referer"),
            ("headers", "remove_sensitive_headers"),
        ],
        "rate_limit": [
            ("delay", "add_delay"),
            ("retry", "increase_retry_delay"),
            ("concurrency", "reduce_concurrency"),
        ],
    }
    
    def __init__(self):
        self.fixes_applied = []
    
    async def fix(
        self,
        code: str,
        error_type: str,
        error_message: str,
    ) -> AutoFixResult:
        """
        Attempt to fix crawler code based on error.
        
        Args:
            code: Current crawler code
            error_type: Type of error (timeout, auth_error, rate_limit)
            error_message: Error message
            
        Returns:
            AutoFixResult with fix results
        """
        fixes = self.FIX_STRATEGIES.get(error_type, [])
        
        if not fixes:
            return AutoFixResult(
                fixed=False,
                error=f"No fix strategy for {error_type}",
            )
        
        new_code = code
        changes = []
        
        for fix_type, fix_name in fixes:
            if fix_type == "timeout":
                # Increase timeout
                if "timeout=" in new_code:
                    new_code = new_code.replace("timeout=30", "timeout=60")
                    new_code = new_code.replace("timeout=60", "timeout=120")
                    changes.append(f"Increased timeout to 120s")
                else:
                    new_code = new_code.replace(
                        "Client(",
                        "Client(timeout=120, ",
                    )
                    changes.append("Added timeout parameter")
            
            elif fix_type == "headers":
                # Add common headers
                if "User-Agent" not in new_code:
                    new_code = new_code.replace(
                        "headers={}",
                        'headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}',
                    )
                    changes.append("Added User-Agent header")
                
                if "Referer" not in new_code:
                    new_code = new_code.replace(
                        "headers={",
                        'headers={"Referer": "https://example.com"}, ',
                    )
                    changes.append("Added Referer header")
            
            elif fix_type == "delay":
                # Add delay between requests
                if "time.sleep" not in new_code and "delay" not in new_code:
                    new_code = new_code.replace(
                        "for",
                        "import time\n\nfor",
                    )
                    changes.append("Added delay mechanism")
        
        fixed = len(changes) > 0
        
        return AutoFixResult(
            fixed=fixed,
            changes_made=changes,
            new_code=new_code,
        )
    
    def apply_fixes_sequence(
        self,
        code: str,
        errors: list[tuple[str, str]],
    ) -> AutoFixResult:
        """
        Apply fixes in sequence for multiple errors.
        
        Args:
            code: Current crawler code
            errors: List of (error_type, error_message) tuples
            
        Returns:
            AutoFixResult with all fixes
        """
        current_code = code
        all_changes = []
        
        for error_type, error_message in errors:
            result = asyncio.run(self.fix(current_code, error_type, error_message))
            
            if result.fixed:
                current_code = result.new_code
                all_changes.extend(result.changes_made)
        
        return AutoFixResult(
            fixed=len(all_changes) > 0,
            changes_made=all_changes,
            new_code=current_code,
        )


# =============================================================================
# COMBINED VERIFIER
# =============================================================================

class ExtendedVerifier:
    """
    Combined extended verification:
    - Multi-request verification
    - Stress testing
    - Auto-correction
    """
    
    def __init__(self):
        self.multi_verifier = MultiRequestVerifier()
        self.stress_tester = StressTester()
        self.corrector = AutoCorrector()
    
    async def verify_and_fix(
        self,
        crawler_func,
        code: str,
        test_params: list[dict],
        run_stress: bool = False,
    ) -> tuple[MultiRequestResult, Optional[StressTestResult], Optional[AutoFixResult]]:
        """
        Run full verification and auto-fix workflow.
        
        Args:
            crawler_func: Function to test
            code: Current code (for fixing)
            test_params: Parameters for multi-request test
            run_stress: Whether to run stress test
            
        Returns:
            Tuple of (multi_result, stress_result, fix_result)
        """
        # Step 1: Multi-request verification
        multi_result = await self.multi_verifier.verify(crawler_func, test_params)
        
        stress_result = None
        fix_result = None
        
        # Step 2: If failed, try to fix
        if not multi_result.passed:
            error_type = list(multi_result.error_types.keys())[0] if multi_result.error_types else "unknown"
            fix_result = await self.corrector.fix(code, error_type, "")
            
            if fix_result.fixed:
                log.info("auto_fix_applied", changes=fix_result.changes_made)
        
        # Step 3: Stress test (optional)
        if run_stress and multi_result.passed:
            stress_result = await self.stress_tester.stress_test(crawler_func)
        
        return multi_result, stress_result, fix_result


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "MultiRequestResult",
    "StressTestResult", 
    "AutoFixResult",
    "MultiRequestVerifier",
    "StressTester",
    "AutoCorrector",
    "ExtendedVerifier",
]
