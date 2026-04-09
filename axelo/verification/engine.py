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

        is_bridge_mode = generated.output_mode == "bridge"

        for attempt in range(1, MAX_RETRIES + 1):
            log.info("verify_attempt", attempt=attempt, script=str(script_path))

            if is_bridge_mode:
                # Bridge-mode crawlers depend on a live browser context; raw HTTP replay
                # will always fail.  Execute the crawler subprocess to get headers and
                # generated data, then score on data quality + header presence only.
                execution = await self._replay_executor.execute_crawl(script_path, target)
                if execution.error:
                    replay_result = ReplayResult(ok=False, error=execution.error, status_code=0)
                    gen_headers: dict[str, str] = {}
                else:
                    gen_headers = execution.headers or {}
                    replay_result = ReplayResult(
                        ok=bool(gen_headers),
                        status_code=0,
                        headers=gen_headers,
                        output_path=execution.output_path,
                        generated_data=execution.crawl_data,
                    )
            else:
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

            if is_bridge_mode:
                # Bridge-mode: Execute crawler subprocess to get headers AND data.
                # Score based on: header presence + data quality + stability.
                # IMPORTANT: Also check if the response indicates anti-bot blocking.
                from axelo.verification.antibot_detector import get_detector
                antibot_detector = get_detector()
                is_blocked, block_reason = antibot_detector.is_antibot_response(replay_result.generated_data)
                
                # GENERIC: For bridge mode, still try to compare headers if we have ground truth
                # This allows us to verify header format matches even in bridge mode
                if target.target_requests:
                    compare_result = self._header_comparator.compare(
                        gen_headers, 
                        target.target_requests[0]
                    )
                    # Combine with anti-bot check
                    compare_result.ok = compare_result.ok and not is_blocked
                    if is_blocked:
                        compare_result.score *= 0.5  # Penalty for anti-bot detection
                else:
                    # No ground truth, just check headers exist and not blocked
                    compare_result = CompareResult(
                        ok=bool(gen_headers) and not is_blocked,
                        field_results=[],
                        matched=list(gen_headers.keys()),
                        missing=[],
                        score=1.0 if (gen_headers and not is_blocked) else 0.0,
                    )
                
                # If blocked by anti-bot, add diagnostic note
                if is_blocked:
                    log.warning("verify_antibot_detected_in_bridge", reason=block_reason)
            else:
                compare_result = (
                    self._header_comparator.compare(gen_headers, target.target_requests[0])
                    if target.target_requests
                    else None
                )
            data_quality = self._data_quality.evaluate(
                replay_result.generated_data,
                dataset_contract=target.dataset_contract if target.dataset_contract else None,
            )
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
            resource_kind = target.intent.resource_kind if target.intent else ""
            resource_kind_ok = _validate_resource_kind_alignment(replay_result.generated_data, resource_kind)
            overall_ok = live_ok and format_ok and quality_ok and stability_ok and resource_kind_ok

            score_parts = [
                compare_result.score if compare_result else (1.0 if live_ok else 0.0),
                data_quality.score,
                stability.score,
            ]
            
            # P5.1: 加权评分 - 数据质量权重更高
            weights = [0.3, 0.5, 0.2]  # header, data, stability
            weighted_score = sum(s * w for s, w in zip(score_parts, weights))
            score = round(weighted_score, 3)
            
            # P5.2: 最小分数保护 - 如果有任一非零分数，整体给予保护
            min_nonzero = min((s for s in score_parts if s > 0), default=0)
            if min_nonzero > 0:
                score = max(score, 0.3)  # 至少有30%

            report_lines = [f"=== verification report (attempt {attempt}) ==="]
            if compare_result:
                report_lines.append(compare_result.summary())
            if not resource_kind_ok:
                report_lines.append(
                    f"resource_kind_mismatch: response data structure does not match '{resource_kind}' "
                    "(expected list of objects, got list of scalars or wrong shape)"
                )
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


def _validate_resource_kind_alignment(response_data: object, resource_kind: str) -> bool:
    """Generic structural check: verify that the response data shape is consistent
    with the declared resource_kind.  No site-specific logic — only data shape
    heuristics.

    Returns True when the check passes or when there is insufficient data to
    make a determination (so verification is never blocked on missing data).
    """
    if not resource_kind or resource_kind == "generic_resource":
        return True
    if response_data is None:
        return True

    items: list | None = None
    if isinstance(response_data, list):
        items = response_data
    elif isinstance(response_data, dict):
        # First try well-known product/data collection keys.
        for key in ("data", "items", "results", "products", "list", "records"):
            val = response_data.get(key)
            if isinstance(val, list) and val:
                items = val
                break
        # If no canonical key matched, scan ALL values for a non-empty list.
        # This catches endpoints that use domain-specific list keys (e.g.
        # "suggestions", "entries", "hits", etc.) which must still satisfy the
        # resource_kind contract.
        if items is None:
            for val in response_data.values():
                if isinstance(val, list) and val:
                    items = val
                    break

    # Cannot determine shape without a non-empty list — pass through.
    if not items:
        return True

    if resource_kind in ("product_listing", "search_results", "reviews", "content_listing"):
        # Step 1: items must be structured dicts, not bare scalars/strings.
        if not isinstance(items[0], dict):
            return False

        # Step 2: for product_listing, at least one item must contain a key
        # associated with product identity or pricing.  This catches endpoints
        # that return lists of dicts but for a completely different domain
        # (e.g. a list of search-suggestion objects with "value"/"type" keys).
        if resource_kind == "product_listing":
            _PRODUCT_IDENTITY_KEYS = frozenset({
                "id", "asin", "sku", "itemid", "item_id", "productid", "product_id",
                "title", "name", "price", "url", "href", "image",
            })
            sample_keys = frozenset(items[0].keys())
            if not (sample_keys & _PRODUCT_IDENTITY_KEYS):
                return False

    return True


__all__ = ["VerificationEngine", "VerificationResult", "_detect_risk_control", "_validate_resource_kind_alignment"]
