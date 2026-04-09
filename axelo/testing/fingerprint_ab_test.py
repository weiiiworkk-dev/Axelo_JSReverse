"""Cap-8: A/B fingerprint comparison test framework.

Measures the actual pass-rate difference between two BrowserProfile configurations
against a target URL by running N alternating trials and comparing outcomes
with Fisher's exact test for statistical significance.

Usage::

    tester = FingerprintABTester()
    result = await tester.run(ABTestConfig(
        name="screen_fix_vs_baseline",
        control_profile=BrowserProfile(),
        variant_profile=BrowserProfile(environment_simulation=...),
        target_url="https://target.example.com/",
        n_trials=10,
    ))
    print(f"Control: {result.control_pass_rate:.0%}, Variant: {result.variant_pass_rate:.0%}")
    print(f"Improvement: {result.improvement:+.1%}, p={result.statistical_significance:.3f}")
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any

import structlog

from axelo.models.target import BrowserProfile

log = structlog.get_logger()


@dataclass
class ABTestConfig:
    """Configuration for one A/B fingerprint test."""
    name: str
    control_profile: BrowserProfile      # baseline (current default)
    variant_profile: BrowserProfile      # new config being tested
    target_url: str
    n_trials: int = 10                   # trials per group (total = 2 × n_trials)
    timeout_per_trial: float = 30.0      # max seconds per browser request
    delay_between_trials: float = 2.0    # seconds between requests (respect rate limits)


@dataclass
class TrialResult:
    group: str      # "control" | "variant"
    passed: bool
    duration_ms: int
    evidence: list[str] = field(default_factory=list)


@dataclass
class ABTestResult:
    config_name: str
    control_pass_rate: float
    variant_pass_rate: float
    improvement: float                   # variant - control (positive = better)
    statistical_significance: float      # p-value from Fisher's exact test (lower = more significant)
    control_trials: list[TrialResult] = field(default_factory=list)
    variant_trials: list[TrialResult] = field(default_factory=list)
    total_duration_s: float = 0.0

    @property
    def is_significant(self) -> bool:
        """True if p < 0.05 (statistically significant improvement)."""
        return self.statistical_significance < 0.05

    @property
    def summary(self) -> str:
        sig = "SIGNIFICANT" if self.is_significant else "not significant"
        return (
            f"{self.config_name}: "
            f"control={self.control_pass_rate:.0%} "
            f"variant={self.variant_pass_rate:.0%} "
            f"improvement={self.improvement:+.1%} "
            f"p={self.statistical_significance:.3f} ({sig})"
        )


# Type alias for trial function
TrialFn = Callable[[str, BrowserProfile, float], Coroutine[Any, Any, TrialResult]]


async def _default_trial_fn(url: str, profile: BrowserProfile, timeout: float) -> TrialResult:
    """Default trial: fetch the URL using curl_cffi with the given profile.

    Returns passed=True if response is 2xx, passed=False otherwise.
    """
    t0 = time.monotonic()
    evidence: list[str] = []
    try:
        import curl_cffi.requests as cr  # type: ignore[import]
        ua = profile.user_agent or ""
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: cr.get(
                    url,
                    headers={"User-Agent": ua} if ua else {},
                    impersonate="chrome124",
                    timeout=timeout,
                    allow_redirects=True,
                )
            ),
            timeout=timeout + 2,
        )
        status = getattr(resp, "status_code", 0) or 0
        evidence.append(f"status={status}")
        passed = 200 <= status < 400
    except Exception as exc:
        evidence.append(f"error={type(exc).__name__}")
        passed = False

    return TrialResult(
        group="",
        passed=passed,
        duration_ms=int((time.monotonic() - t0) * 1000),
        evidence=evidence,
    )


class FingerprintABTester:
    """Runs alternating control/variant trials and compares pass rates.

    Alternates between control and variant profiles to minimize temporal
    bias (both groups face similar site state).

    Custom trial function:
        If the default HTTP request is insufficient (e.g., you need full
        browser rendering), pass a custom ``trial_fn`` to ``run()``.
    """

    def __init__(self, trial_fn: TrialFn | None = None) -> None:
        self._trial_fn = trial_fn or _default_trial_fn

    async def run(self, config: ABTestConfig) -> ABTestResult:
        """Execute the A/B test and return results."""
        t0 = time.monotonic()
        log.info("ab_test_start", name=config.name, url=config.target_url[:80], n_trials=config.n_trials)

        control_trials: list[TrialResult] = []
        variant_trials: list[TrialResult] = []

        # Alternate: C, V, C, V, ... to balance time effects
        for i in range(config.n_trials):
            for group, profile, trial_list in [
                ("control", config.control_profile, control_trials),
                ("variant", config.variant_profile, variant_trials),
            ]:
                result = await self._trial_fn(config.target_url, profile, config.timeout_per_trial)
                result.group = group
                trial_list.append(result)
                log.debug(
                    "ab_trial_done",
                    group=group,
                    trial=i + 1,
                    passed=result.passed,
                    ms=result.duration_ms,
                )
                if config.delay_between_trials > 0:
                    await asyncio.sleep(config.delay_between_trials)

        control_pass = sum(1 for t in control_trials if t.passed)
        variant_pass = sum(1 for t in variant_trials if t.passed)
        n = config.n_trials

        control_rate = control_pass / max(n, 1)
        variant_rate = variant_pass / max(n, 1)
        improvement = variant_rate - control_rate
        p_value = _fisher_exact_p(control_pass, n - control_pass, variant_pass, n - variant_pass)

        result = ABTestResult(
            config_name=config.name,
            control_pass_rate=control_rate,
            variant_pass_rate=variant_rate,
            improvement=improvement,
            statistical_significance=p_value,
            control_trials=control_trials,
            variant_trials=variant_trials,
            total_duration_s=time.monotonic() - t0,
        )
        log.info("ab_test_done", summary=result.summary, duration=f"{result.total_duration_s:.1f}s")
        return result


def _fisher_exact_p(a: int, b: int, c: int, d: int) -> float:
    """Compute the two-tailed p-value for a 2×2 contingency table using Fisher's exact test.

    Table layout:
        | pass | fail |
    ----+------+------+
    ctrl|  a   |  b   |
    vari|  c   |  d   |

    Uses the hypergeometric distribution via log-factorials.
    Returns 1.0 if table is degenerate.
    """
    n = a + b + c + d
    if n == 0 or (a + c) == 0 or (b + d) == 0:
        return 1.0

    def log_factorial(x: int) -> float:
        import math
        return sum(math.log(i) for i in range(1, x + 1))

    def _p_cell(a: int, b: int, c: int, d: int) -> float:
        import math
        n = a + b + c + d
        try:
            log_p = (
                log_factorial(a + b) + log_factorial(c + d)
                + log_factorial(a + c) + log_factorial(b + d)
                - log_factorial(n) - log_factorial(a)
                - log_factorial(b) - log_factorial(c) - log_factorial(d)
            )
            return math.exp(log_p)
        except Exception:
            return 0.0

    p_observed = _p_cell(a, b, c, d)
    p_total = 0.0
    r1 = a + b  # row 1 total
    r2 = c + d  # row 2 total
    col1 = a + c
    col2 = b + d

    # Sum all tables with the same marginals where P ≤ P_observed
    for a_try in range(max(0, r1 - col2), min(r1, col1) + 1):
        b_try = r1 - a_try
        c_try = col1 - a_try
        d_try = r2 - c_try
        if b_try < 0 or c_try < 0 or d_try < 0:
            continue
        p_try = _p_cell(a_try, b_try, c_try, d_try)
        if p_try <= p_observed + 1e-10:
            p_total += p_try

    return min(1.0, p_total)
