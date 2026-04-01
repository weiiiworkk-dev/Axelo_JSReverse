from __future__ import annotations
import json
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis, AIHypothesis
from axelo.models.codegen import GeneratedCode
from axelo.modes.base import ModeController
from axelo.ai.client import AIClient
from axelo.ai.hypothesis import CodeGenOutput
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent.parent / "ai" / "prompts"


class CodeGenStage(PipelineStage):
    name = "s7_codegen"
    description = "代码生成：根据AI假设生成独立Python脚本或JS桥接服务"

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def run(
        self, state: PipelineState, mode: ModeController,
        hypothesis: AIHypothesis | None,
        static_results: dict[str, StaticAnalysis],
        target: TargetSite,
        dynamic: DynamicAnalysis | None = None,
        **_,
    ) -> StageResult:
        if hypothesis is None:
            return StageResult(
                stage_name=self.name, success=True,
                summary="代码生成已跳过（无假设）",
            )

        session_dir = settings.session_dir(state.session_id)
        output_dir = session_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 准备源码片段
        source_snippets = _collect_snippets(hypothesis, static_results)
        hook_data = _collect_hook_data(dynamic)

        # 获取第一个 bundle 路径（用于桥接模式）
        first_bundle_path = ""
        for bid, sa in static_results.items():
            raw_path = session_dir / "bundles" / f"{bid}.raw.js"
            if raw_path.exists():
                first_bundle_path = str(raw_path)
                break

        # 根据策略选择 prompt
        if hypothesis.codegen_strategy == "python_reconstruct":
            template = self._jinja.get_template("generate_python.j2")
            system_prompt = template.render(
                hypothesis=hypothesis,
                source_snippets=source_snippets,
                hook_data=hook_data,
                target=target,
            )
        else:
            template = self._jinja.get_template("generate_bridge.j2")
            system_prompt = template.render(
                hypothesis=hypothesis,
                bundle_path=first_bundle_path,
                bridge_port=8721,
                target=target,
            )

        user_msg = f"目标URL: {target.url}\n请生成完整的可运行代码。"

        log.info("codegen_start", strategy=hypothesis.codegen_strategy)

        codegen_output: CodeGenOutput = await self._ai.analyze(
            system_prompt=system_prompt,
            user_message=user_msg,
            output_schema=CodeGenOutput,
            tool_name="codegen",
            log_dir=session_dir / "ai_context",
        )

        # 写出生成的文件
        artifacts: dict[str, Path] = {}

        if codegen_output.crawler_code:
            crawler_path = output_dir / "crawler.py"
            crawler_path.write_text(codegen_output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = crawler_path
            log.info("codegen_wrote", file=str(crawler_path))

        if codegen_output.bridge_server_code:
            server_path = output_dir / "bridge_server.js"
            server_path.write_text(codegen_output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = server_path

        # 写依赖说明
        if codegen_output.dependencies:
            deps_path = output_dir / "requirements.txt"
            deps_path.write_text("\n".join(codegen_output.dependencies), encoding="utf-8")
            artifacts["requirements"] = deps_path

        # 决策：审查生成爬虫
        artifact_preview = artifacts.get("crawler_script")
        options = ["接受爬虫代码，进行验证", "重新生成", "直接保存，跳过验证"]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.EDIT_ARTIFACT,
            prompt="爬虫代码生成完成，请审查：",
            options=options,
            artifact_path=artifact_preview,
            context_summary=codegen_output.notes or f"生成文件: {list(artifacts.keys())}",
            default="接受爬虫代码，进行验证",
        )

        outcome = await mode.gate(decision, state)

        if outcome == options[1]:
            return await self.run(state, mode, hypothesis=hypothesis, static_results=static_results,
                                  target=target, dynamic=dynamic)

        generated = GeneratedCode(
            session_id=state.session_id,
            output_mode="standalone" if not codegen_output.bridge_server_code else "bridge",
            crawler_script_path=artifacts.get("crawler_script"),
            crawler_deps=codegen_output.dependencies,
            bridge_server_path=artifacts.get("bridge_server"),
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts=artifacts,
            decisions=[decision],
            summary=f"生成文件: {[str(p.name) for p in artifacts.values()]}",
            next_input={"generated": generated},
        )


def _collect_snippets(hypothesis: AIHypothesis, static_results: dict) -> str:
    snippets = []
    for sa in static_results.values():
        for candidate in sa.token_candidates:
            if candidate.func_id in hypothesis.generator_func_ids:
                if candidate.source_snippet:
                    snippets.append(f"// {candidate.func_id}\n{candidate.source_snippet}")
    return "\n\n".join(snippets[:5]) or "（未找到对应源码片段）"


def _collect_hook_data(dynamic: DynamicAnalysis | None) -> str:
    if not dynamic or not dynamic.hook_intercepts:
        return "（无动态数据）"
    sample = dynamic.hook_intercepts[:5]
    return json.dumps([ic.model_dump(mode="json") for ic in sample], ensure_ascii=False, indent=2)
