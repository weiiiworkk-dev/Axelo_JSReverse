from __future__ import annotations

import json
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

from axelo.ai.client import AIClient
from axelo.ai.hypothesis import CodeGenOutput
from axelo.config import settings
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.codegen import GeneratedCode
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent.parent / "ai" / "prompts"


class CodeGenStage(PipelineStage):
    name = "s7_codegen"
    description = "Generate runnable crawler code and a manifest from the AI hypothesis."

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        hypothesis: AIHypothesis | None,
        static_results: dict[str, StaticAnalysis],
        target: TargetSite,
        dynamic: DynamicAnalysis | None = None,
        **_,
    ) -> StageResult:
        if hypothesis is None:
            return StageResult(stage_name=self.name, success=True, summary="Code generation skipped")

        session_dir = settings.session_dir(state.session_id)
        output_dir = session_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        source_snippets = _collect_snippets(hypothesis, static_results)
        hook_data = _collect_hook_data(dynamic)

        if hypothesis.codegen_strategy == "python_reconstruct":
            template = self._jinja.get_template("generate_python.j2")
            system_prompt = template.render(hypothesis=hypothesis, source_snippets=source_snippets, hook_data=hook_data, target=target)
        else:
            first_bundle_path = next((str(session_dir / "bundles" / f"{bundle_id}.raw.js") for bundle_id in static_results), "")
            template = self._jinja.get_template("generate_bridge.j2")
            system_prompt = template.render(hypothesis=hypothesis, bundle_path=first_bundle_path, bridge_port=8721, target=target)

        codegen_output: CodeGenOutput = await self._ai.analyze(
            system_prompt=system_prompt,
            user_message=f"Target URL: {target.url}\nGenerate complete runnable code.",
            output_schema=CodeGenOutput,
            tool_name="codegen",
            log_dir=session_dir / "ai_context",
        )

        artifacts: dict[str, Path] = {}
        if codegen_output.crawler_code:
            crawler_path = output_dir / "crawler.py"
            crawler_path.write_text(codegen_output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = crawler_path
        if codegen_output.bridge_server_code:
            bridge_path = output_dir / "bridge_server.js"
            bridge_path.write_text(codegen_output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = bridge_path
        if codegen_output.dependencies:
            deps_path = output_dir / "requirements.txt"
            deps_path.write_text("\n".join(codegen_output.dependencies), encoding="utf-8")
            artifacts["requirements"] = deps_path

        manifest_path = output_dir / "crawler_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "strategy": hypothesis.codegen_strategy,
                    "signature_spec": hypothesis.signature_spec.model_dump(mode="json") if hypothesis.signature_spec else None,
                    "dependencies": codegen_output.dependencies,
                    "notes": codegen_output.notes,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        artifacts["manifest"] = manifest_path

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.EDIT_ARTIFACT,
            prompt="Generated crawler artifacts are ready. Continue to verification?",
            options=["verify", "regenerate", "save_without_verify"],
            artifact_path=artifacts.get("crawler_script"),
            context_summary=codegen_output.notes or f"files={list(artifacts.keys())}",
            default="verify",
        )
        outcome = await mode.gate(decision, state)
        if outcome == "regenerate":
            return await self.run(state, mode, hypothesis=hypothesis, static_results=static_results, target=target, dynamic=dynamic)

        generated = GeneratedCode(
            session_id=state.session_id,
            output_mode="standalone" if not codegen_output.bridge_server_code else "bridge",
            crawler_script_path=artifacts.get("crawler_script"),
            crawler_deps=codegen_output.dependencies,
            bridge_server_path=artifacts.get("bridge_server"),
            manifest_path=manifest_path,
        )
        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts=artifacts,
            decisions=[decision],
            summary=f"Generated files: {[path.name for path in artifacts.values()]}",
            next_input={"generated": generated},
        )


def _collect_snippets(hypothesis: AIHypothesis, static_results: dict[str, StaticAnalysis]) -> str:
    snippets = []
    for static in static_results.values():
        for candidate in static.token_candidates:
            if candidate.func_id in hypothesis.generator_func_ids and candidate.source_snippet:
                snippets.append(f"// {candidate.func_id}\n{candidate.source_snippet}")
    return "\n\n".join(snippets[:5]) or "(no matching snippets found)"


def _collect_hook_data(dynamic: DynamicAnalysis | None) -> str:
    if not dynamic or not dynamic.hook_intercepts:
        return "(no dynamic data)"
    sample = dynamic.hook_intercepts[:5]
    return json.dumps([item.model_dump(mode="json") for item in sample], ensure_ascii=False, indent=2)
