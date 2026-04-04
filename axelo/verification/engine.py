from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from axelo.models.codegen import GeneratedCode
from axelo.models.execution import VerificationMode
from axelo.models.target import TargetSite
from axelo.verification.comparator import CompareResult, TokenComparator
from axelo.verification.data_quality import DataQualityResult, evaluate_data_quality
from axelo.verification.replayer import CrawlExecutionResult, ReplayResult, RequestReplayer
from axelo.verification.stability import StabilityResult, evaluate_stability

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
        self._replayer = RequestReplayer()
        self._comparator = TokenComparator()

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
            return VerificationResult(ok=True, score=1.0, strategy_used=generated.output_mode, report="verification skipped by execution plan")

        stability_samples: list[tuple[dict[str, str], object]] = []

        for attempt in range(1, MAX_RETRIES + 1):
            log.info("verify_attempt", attempt=attempt, script=str(script_path))

            gen_headers, replay_result = await self._replayer.replay_with_script(script_path, target)
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

            compare_result: CompareResult | None = None
            if target.target_requests:
                compare_result = self._comparator.compare(gen_headers, target.target_requests[0])

            if verification_mode == VerificationMode.BASIC:
                data_quality = evaluate_data_quality(replay_result.generated_data)
                stability = StabilityResult(ok=True, score=1.0, runs=max(1, len(stability_samples)), consistent_header_keys=True, consistent_output_shape=True)
            else:
                data_quality = evaluate_data_quality(replay_result.generated_data)
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
            risk_control_reason = _detect_risk_control(replay_result)
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

            retry_reason = _diagnose_failure(compare_result, replay_result, data_quality, stability)
            log.info("verify_retry", reason=retry_reason, attempt=attempt)
            result.retry_reason = retry_reason

        return VerificationResult(ok=False, attempts=MAX_RETRIES, report="exceeded maximum retry attempts")

    async def _stability_check(
        self,
        script_path: Path,
        target: TargetSite,
        existing_samples: list[tuple[dict[str, str], object]],
    ) -> StabilityResult:
        samples = list(existing_samples)
        desired_runs = max(1, target.compliance.stability_runs)
        verification_mode = target.execution_plan.verification_mode if target.execution_plan else VerificationMode.STANDARD
        if verification_mode == VerificationMode.BASIC:
            desired_runs = 1
        elif verification_mode == VerificationMode.STRICT:
            desired_runs = max(desired_runs, 3)
        while len(samples) < desired_runs:
            execution: CrawlExecutionResult = await self._replayer.execute_crawl(script_path, target)
            if execution.error:
                break
            samples.append((execution.headers, execution.crawl_data))
        return evaluate_stability(samples)


def _diagnose_failure(
    compare: CompareResult | None,
    replay: ReplayResult,
    data_quality: DataQualityResult,
    stability: StabilityResult,
) -> str:
    risk_control_reason = _detect_risk_control(replay)
    if risk_control_reason:
        return risk_control_reason
    if not replay.ok and replay.status_code == 403:
        return "HTTP 403: signature rejected or session blocked"
    if not replay.ok and replay.status_code == 401:
        return "HTTP 401: authentication failed"
    if compare and compare.missing:
        return f"missing fields: {compare.missing}"
    if compare and compare.score < 0.5:
        return f"header format mismatch: {compare.score:.0%}"
    if not data_quality.ok:
        return f"data quality too low: {data_quality.notes}"
    if not stability.ok:
        return f"stability check failed: {stability.notes}"
    return "unknown verification failure"


def _detect_risk_control(replay: ReplayResult) -> str:
    signal_text = "\n".join(
        part for part in [replay.response_body or "", replay.error or ""] if part
    ).lower()
    if not signal_text:
        return ""
    if "x5secdata" in signal_text or "/_____tmd_____/punish" in signal_text:
        return "risk-control challenge page detected"
    if "rgv587_error" in signal_text or "fail_sys_user_validate" in signal_text:
        return "risk-control validation rejected the replay request"
    return ""
