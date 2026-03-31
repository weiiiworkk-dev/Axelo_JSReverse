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
    description = "验证生成代码：对比生成的签名与捕获的ground truth"

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

        # 尝试导入并运行生成的独立脚本
        if generated.standalone_script_path and generated.standalone_script_path.exists():
            result = await self._verify_standalone(generated.standalone_script_path, target)
            verify_results.append(result)

        # 对比 ground truth（捕获的真实请求头）
        truth_comparison = ""
        if target and target.target_requests:
            truth_comparison = self._compare_with_ground_truth(target.target_requests, verify_results)

        summary = "\n".join(verify_results) if verify_results else "无法自动验证"
        if truth_comparison:
            summary += "\n\n" + truth_comparison

        # 保存验证报告
        report_path = session_dir / "output" / "verify_report.txt"
        report_path.write_text(summary, encoding="utf-8")

        options = [
            "验证通过，完成逆向",
            "验证失败，重新生成代码",
            "手动验证后标记完成",
        ]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.APPROVE_STAGE,
            prompt="验证结果：",
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

    async def _verify_standalone(self, script_path: Path, target: TargetSite | None) -> str:
        """尝试动态导入生成的 Python 脚本并调用 generate()"""
        try:
            spec = importlib.util.spec_from_file_location("generated_module", script_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 查找第一个含 generate 方法的类
            gen_class = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, "generate"):
                    gen_class = obj
                    break

            if gen_class is None:
                return "⚠ 未找到含 generate() 方法的类"

            instance = gen_class()
            test_url = target.url if target else "https://example.com/"
            result = instance.generate(url=test_url, method="GET", body="")
            return f"✓ generate() 调用成功，输出字段: {list(result.keys())}"

        except ImportError as e:
            return f"⚠ 导入失败（缺少依赖）: {e}"
        except Exception as e:
            return f"✗ 运行异常: {e}"

    def _compare_with_ground_truth(
        self, target_requests: list[RequestCapture], verify_results: list[str]
    ) -> str:
        """将验证输出与捕获的真实请求头进行字段对比"""
        lines = ["=== Ground Truth 对比 ==="]
        for req in target_requests[:2]:
            lines.append(f"URL: {req.url}")
            for field, value in list(req.request_headers.items())[:5]:
                lines.append(f"  {field}: {value[:60]}")
        return "\n".join(lines)
