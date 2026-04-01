from __future__ import annotations
import asyncio
import importlib.util
import sys
from pathlib import Path
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite, RequestCapture
from axelo.models.codegen import GeneratedCode
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()


class VerifyStage(PipelineStage):
    name = "s8_verify"
    description = "验证生成爬虫：运行 crawl() 确认能正常返回数据"

    async def run(
        self, state: PipelineState, mode: ModeController,
        generated: GeneratedCode | None = None,
        target: TargetSite | None = None,
        **_,
    ) -> StageResult:
        if generated is None:
            return StageResult(
                stage_name=self.name, success=True,
                summary="验证跳过（无生成代码）",
            )

        session_dir = settings.session_dir(state.session_id)
        verify_results: list[str] = []

        # 运行生成的爬虫脚本
        if generated.crawler_script_path and generated.crawler_script_path.exists():
            result = await self._verify_crawler(generated.crawler_script_path, target)
            verify_results.append(result)

        # 对比 ground truth（捕获的真实请求头）
        truth_comparison = ""
        if target and target.target_requests:
            truth_comparison = self._compare_with_ground_truth(target.target_requests)

        summary = "\n".join(verify_results) if verify_results else "无法自动验证"
        if truth_comparison:
            summary += "\n\n" + truth_comparison

        # 保存验证报告
        report_path = session_dir / "output" / "verify_report.txt"
        report_path.write_text(summary, encoding="utf-8")

        options = [
            "验证通过，爬虫可用",
            "验证失败，重新生成代码",
            "手动验证后标记完成",
        ]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.APPROVE_STAGE,
            prompt="爬虫验证结果：",
            options=options,
            artifact_path=report_path,
            context_summary=summary[:500],
            default="手动验证后标记完成",
        )

        outcome = await mode.gate(decision, state)

        if generated:
            generated.verified = (outcome == options[0])
            generated.verification_notes = summary

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"verify_report": report_path},
            decisions=[decision],
            summary=f"验证完成: {outcome}",
        )

    async def _verify_crawler(self, script_path: Path, target: TargetSite | None) -> str:
        """动态导入生成的爬虫脚本，调用 crawl() 确认能正常执行"""
        try:
            spec = importlib.util.spec_from_file_location("generated_crawler", script_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 查找第一个含 crawl 方法的类
            crawler_class = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "crawl"):
                    crawler_class = obj
                    break

            if crawler_class is None:
                return "⚠ 未找到含 crawl() 方法的类"

            instance = crawler_class()
            result = instance.crawl()
            if isinstance(result, dict):
                keys = list(result.keys())[:5]
                return f"✓ crawl() 调用成功，返回字段: {keys}"
            return f"✓ crawl() 调用成功，返回类型: {type(result).__name__}"

        except ImportError as e:
            return f"⚠ 导入失败（缺少依赖）: {e}"
        except Exception as e:
            return f"✗ 运行异常: {e}"

    def _compare_with_ground_truth(self, target_requests: list[RequestCapture]) -> str:
        """显示捕获的真实请求作为参考"""
        lines = ["=== 捕获的真实请求（参考） ==="]
        for req in target_requests[:2]:
            lines.append(f"URL: {req.url}")
            for field, value in list(req.request_headers.items())[:5]:
                lines.append(f"  {field}: {value[:60]}")
        return "\n".join(lines)
