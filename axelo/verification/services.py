from __future__ import annotations

from pathlib import Path

from axelo.domain.services import RiskControlService
from axelo.models.execution import VerificationMode
from axelo.models.target import TargetSite
from axelo.verification.comparator import CompareResult, TokenComparator
from axelo.verification.data_quality import DataQualityResult, evaluate_data_quality
from axelo.verification.replayer import CrawlExecutionResult, ReplayResult, RequestReplayer
from axelo.verification.stability import StabilityResult, evaluate_stability


class ReplayExecutor:
    def __init__(self) -> None:
        self._replayer = RequestReplayer()

    async def replay_with_script(self, script_path: Path, target: TargetSite) -> tuple[dict[str, str], ReplayResult]:
        return await self._replayer.replay_with_script(script_path, target)

    async def execute_crawl(self, script_path: Path, target: TargetSite) -> CrawlExecutionResult:
        return await self._replayer.execute_crawl(script_path, target)


class HeaderComparator:
    def __init__(self) -> None:
        self._comparator = TokenComparator()

    def compare(self, gen_headers: dict[str, str], target_request) -> CompareResult:
        return self._comparator.compare(gen_headers, target_request)


class DataQualityEvaluator:
    def evaluate(self, generated_data, dataset_contract=None) -> DataQualityResult:
        return evaluate_data_quality(generated_data, dataset_contract=dataset_contract)


class StabilityEvaluator:
    def __init__(self, replay_executor: ReplayExecutor) -> None:
        self._replay_executor = replay_executor

    async def evaluate(
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
            execution = await self._replay_executor.execute_crawl(script_path, target)
            if execution.error:
                break
            samples.append((execution.headers, execution.crawl_data))
        return evaluate_stability(samples)


class RiskControlDetector:
    def __init__(self, service: RiskControlService | None = None) -> None:
        self._service = service or RiskControlService()

    def detect(self, replay: ReplayResult) -> str:
        return self._service.detect_replay(replay)


def diagnose_failure(
    *,
    compare: CompareResult | None,
    replay: ReplayResult,
    data_quality: DataQualityResult,
    stability: StabilityResult,
    risk_control_detector: RiskControlDetector,
) -> str:
    # === Enhanced: Check anti-bot first ===
    from axelo.verification.antibot_detector import get_detector
    antibot_detector = get_detector()
    is_blocked, block_reason = antibot_detector.is_antibot_response(replay.generated_data)
    if is_blocked:
        return f"ANTI_BOT_DETECTED: {block_reason}"
    # === End enhanced check ===
    
    risk_control_reason = risk_control_detector.detect(replay)
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
