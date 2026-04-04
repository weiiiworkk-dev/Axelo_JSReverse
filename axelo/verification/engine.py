from __future__ import annotations

from dataclasses import dataclass

import structlog

from axelo.models.codegen import GeneratedCode
from axelo.models.execution import VerificationMode
from axelo.models.target import TargetSite
from axelo.verification.comparator import CompareResult
from axelo.verification.data_quality import DataQualityResult
from axelo.verification.replayer import ReplayResult
from axelo.verification.services import (
    DataQualityEvaluator,
    HeaderComparator,
    ReplayExecutor,
    RiskControlDetector,
    StabilityEvaluator,
    diagnose_failure,
)
from axelo.verification.stability import StabilityResult

log = structlog.get_logger()

MAX_RETRIES = 3


@dataclass
class VerificationResult:
    ok: bool
    score: float = 0.0
    replay: ReplayResult | None = None
    compare: CompareResult | None = None
    data_quality: DataQualityResult | None = None
    stability: StabilityResult | None = None
    attempts: int = 0
    strategy_used: str = ""
    report: str = ""
    retry_reason: str = ""
    risk_control_reason: str = ""


class VerificationEngine:
    """Verify generated code by replaying requests, checking data quality, and measuring stability."""

    def __init__(self) -> None:
        self._replay_executor = ReplayExecutor()
        self._header_comparator = HeaderComparator()
        self._data_quality = DataQualityEvaluator()
        self._stability = StabilityEvaluator(self._replay_executor)
        self._risk_control = RiskControlDetector()
        self._replayer = self._replay_executor
        self._comparator = self._header_comparator

    async def verify(
        self,
        generated: GeneratedCode,
        target: TargetSite,
        live_verify: bool = True,
    ) -> VerificationResult:
        script_path = generated.crawler_script_path
        if script_path is None or not script_path.exists():
            return VerificationResult(ok=False, report="verification failed: generated crawler file is missing")

        verification_mode = target.execution_plan.verification_mode if target.execution_plan else VerificationMode.STANDARD
        if verification_mode == VerificationMode.NONE:
            return VerificationResult(
                ok=True,
                score=1.0,
                strategy_used=generated.output_mode,
                report="verification skipped by execution plan",
            )

        stability_samples: list[tuple[dict[str, str], object]] = []

        for attempt in range(1, MAX_RETRIES + 1):
            log.info("verify_attempt", attempt=attempt, script=str(script_path))
            gen_headers, replay_result = await self._replay_executor.replay_with_script(script_path, target)
            if replay_result.generated_data is not None:
                stability_samples.append((gen_headers, replay_result.generated_data))

            if not gen_headers:
                if attempt < MAX_RETRIES:
                    log.warning("verify_no_headers", attempt=attempt)
                    continue
                return VerificationResult(
                    ok=False,
                    attempts=attempt,
                    replay=replay_result,
                    report=f"crawl() execution failed: {replay_result.error}",
                )

            compare_result = (
                self._header_comparator.compare(gen_headers, target.target_requests[0])
                if target.target_requests
                else None
            )
            data_quality = self._data_quality.evaluate(replay_result.generated_data)
            if verification_mode == VerificationMode.BASIC:
                stability = StabilityResult(
                    ok=True,
                    score=1.0,
                    runs=max(1, len(stability_samples)),
                    consistent_header_keys=True,
                    consistent_output_shape=True,
                )
            else:
                stability = await self._stability_check(script_path, target, stability_samples)

            live_ok = (not live_verify) or replay_result.ok
            format_ok = compare_result.ok if compare_result else True
            quality_ok = data_quality.ok
            stability_ok = stability.ok
            overall_ok = live_ok and format_ok and quality_ok and stability_ok

            score_parts = [
                compare_result.score if compare_result else (1.0 if live_ok else 0.0),
                data_quality.score,
                stability.score,
            ]
            score = round(sum(score_parts) / len(score_parts), 3)

            report_lines = [f"=== verification report (attempt {attempt}) ==="]
            if compare_result:
                report_lines.append(compare_result.summary())
            risk_control_reason = self._risk_control.detect(replay_result)
            if risk_control_reason:
                report_lines.append(f"risk_control detected: {risk_control_reason}")
            report_lines.append(replay_result.summary())
            report_lines.append(data_quality.summary())
            report_lines.append(stability.summary())

            result = VerificationResult(
                ok=overall_ok and not bool(risk_control_reason),
                score=score,
                replay=replay_result,
                compare=compare_result,
                data_quality=data_quality,
                stability=stability,
                attempts=attempt,
                strategy_used=generated.output_mode,
                report="\n".join(report_lines),
                risk_control_reason=risk_control_reason,
            )

            if risk_control_reason:
                result.retry_reason = risk_control_reason
                log.warning("risk_control_detected", attempt=attempt, reason=risk_control_reason)
                return result

            if overall_ok or attempt == MAX_RETRIES:
                return result

            retry_reason = diagnose_failure(
                compare=compare_result,
                replay=replay_result,
                data_quality=data_quality,
                stability=stability,
                risk_control_detector=self._risk_control,
            )
            log.info("verify_retry", reason=retry_reason, attempt=attempt)
            result.retry_reason = retry_reason

        return VerificationResult(ok=False, attempts=MAX_RETRIES, report="exceeded maximum retry attempts")

    async def _stability_check(
        self,
        script_path,
        target: TargetSite,
        existing_samples: list[tuple[dict[str, str], object]],
    ) -> StabilityResult:
        return await self._stability.evaluate(script_path, target, existing_samples)


def _detect_risk_control(replay: ReplayResult) -> str:
    return RiskControlDetector().detect(replay)


__all__ = ["VerificationEngine", "VerificationResult", "_detect_risk_control"]
