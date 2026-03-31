from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite
from axelo.verification.replayer import RequestReplayer, ReplayResult
from axelo.verification.comparator import TokenComparator, CompareResult
import structlog

log = structlog.get_logger()

MAX_RETRIES = 3


@dataclass
class VerificationResult:
    ok: bool
    score: float = 0.0
    replay: ReplayResult | None = None
    compare: CompareResult | None = None
    attempts: int = 0
    strategy_used: str = ""
    report: str = ""
    retry_reason: str = ""


class VerificationEngine:
    """
    验证生成代码的正确性。

    流程：
    1. 用生成脚本产生 headers
    2. 实际发送请求（可选）
    3. 格式比对 generated headers vs ground truth
    4. 失败时根据错误类型切换策略重试
    """

    def __init__(self) -> None:
        self._replayer = RequestReplayer()
        self._comparator = TokenComparator()

    async def verify(
        self,
        generated: GeneratedCode,
        target: TargetSite,
        live_verify: bool = True,
    ) -> VerificationResult:
        """
        live_verify=True：实际发送请求（需要网络）
        live_verify=False：只做格式比对（离线安全）
        """
        script_path = generated.standalone_script_path

        if script_path is None or not script_path.exists():
            return VerificationResult(
                ok=False,
                report="验证失败：未找到生成的脚本文件",
            )

        for attempt in range(1, MAX_RETRIES + 1):
            log.info("verify_attempt", attempt=attempt, script=str(script_path))

            gen_headers, replay_result = await self._replayer.replay_with_script(
                script_path, target
            )

            # 无法生成 headers
            if not gen_headers:
                if attempt < MAX_RETRIES:
                    log.warning("verify_no_headers", attempt=attempt)
                    continue
                return VerificationResult(
                    ok=False,
                    attempts=attempt,
                    replay=replay_result,
                    report=f"generate() 未返回任何字段: {replay_result.error}",
                )

            # 格式比对
            compare_result: CompareResult | None = None
            if target.target_requests:
                compare_result = self._comparator.compare(gen_headers, target.target_requests[0])

            # 综合判断
            live_ok = (not live_verify) or replay_result.ok
            format_ok = compare_result.ok if compare_result else True
            overall_ok = live_ok and format_ok
            score = compare_result.score if compare_result else (1.0 if live_ok else 0.0)

            report_lines = [f"=== 验证报告（第 {attempt} 次）==="]
            if compare_result:
                report_lines.append(compare_result.summary())
            report_lines.append(replay_result.summary())

            result = VerificationResult(
                ok=overall_ok,
                score=score,
                replay=replay_result,
                compare=compare_result,
                attempts=attempt,
                strategy_used="standalone",
                report="\n".join(report_lines),
            )

            if overall_ok or attempt == MAX_RETRIES:
                return result

            # 分析失败原因，决定重试策略
            retry_reason = _diagnose_failure(compare_result, replay_result)
            log.info("verify_retry", reason=retry_reason, attempt=attempt)
            result.retry_reason = retry_reason

        return VerificationResult(ok=False, attempts=MAX_RETRIES, report="超过最大重试次数")


def _diagnose_failure(compare: CompareResult | None, replay: ReplayResult) -> str:
    """分析失败原因，返回诊断描述"""
    if not replay.ok and replay.status_code == 403:
        return "HTTP 403：签名被拒绝，算法可能有误"
    if not replay.ok and replay.status_code == 401:
        return "HTTP 401：认证失败，token 字段可能缺失"
    if compare and compare.missing:
        return f"缺少字段：{compare.missing}"
    if compare and compare.score < 0.5:
        return f"格式匹配率低（{compare.score:.0%}），算法输出格式不对"
    return "未知失败原因"
