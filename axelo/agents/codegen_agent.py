from __future__ import annotations

import json
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader

from axelo.agents.base import BaseAgent
from axelo.ai.hypothesis import CodeGenOutput
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.target import TargetSite

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent / "ai" / "prompts"

CODEGEN_SYSTEM = """You are a crawler code generation agent.

Transform the reverse-engineering result into runnable crawler artifacts.
Always emit complete files, runnable imports, and deterministic helper methods.
"""


class CodeGenAgent(BaseAgent):
    role = "codegen"
    default_model = "claude-opus-4-6"

    def __init__(self, *args, retriever: MemoryRetriever, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def generate(
        self,
        target: TargetSite,
        hypothesis: AIHypothesis,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        output_dir: Path,
    ) -> dict[str, Path]:
        algo_type = _infer_algo_type(hypothesis)
        templates = self._retriever.get_all_templates()
        template_code = ""
        for template_item in templates:
            if template_item.algorithm_type == algo_type and template_item.python_code:
                template_code = f"# reference template '{template_item.name}'\n{template_item.python_code}"
                break

        system_prompt = CODEGEN_SYSTEM + f"\n\nReference template:\n{template_code or '(none)'}"
        source_snippets = _collect_snippets(hypothesis, static_results)
        hook_data = _collect_hook_data(dynamic)

        if hypothesis.codegen_strategy == "python_reconstruct":
            template = self._jinja.get_template("generate_python.j2")
            user_msg = template.render(
                hypothesis=hypothesis,
                source_snippets=source_snippets,
                hook_data=hook_data,
                target=target,
            )
        else:
            first_bundle = next(
                (str(output_dir.parent / "bundles" / f"{bundle_id}.raw.js") for bundle_id in static_results),
                "",
            )
            template = self._jinja.get_template("generate_bridge.j2")
            user_msg = template.render(
                hypothesis=hypothesis,
                bundle_path=first_bundle,
                bridge_port=8721,
                target=target,
            )

        client = self._build_client()
        response = await client.analyze(
            system_prompt=system_prompt,
            user_message=user_msg,
            output_schema=CodeGenOutput,
            tool_name="codegen",
            max_tokens=8192,
        )
        output = response.data

        self._cost.add_ai_call(
            model=response.model,
            input_tok=response.input_tokens,
            output_tok=response.output_tokens,
            stage="codegen",
        )

        artifacts: dict[str, Path] = {}
        output_dir.mkdir(parents=True, exist_ok=True)

        if output.crawler_code:
            path = output_dir / "crawler.py"
            path.write_text(output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = path
        if output.bridge_server_code:
            path = output_dir / "bridge_server.js"
            path.write_text(output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = path
        if output.dependencies:
            path = output_dir / "requirements.txt"
            path.write_text("\n".join(output.dependencies), encoding="utf-8")
            artifacts["requirements"] = path

        manifest = {
            "strategy": hypothesis.codegen_strategy,
            "algorithm_description": hypothesis.algorithm_description,
            "signature_spec": hypothesis.signature_spec.model_dump(mode="json") if hypothesis.signature_spec else None,
            "notes": output.notes,
            "dependencies": output.dependencies,
        }
        manifest_path = output_dir / "crawler_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["manifest"] = manifest_path

        log.info("codegen_done", files=list(artifacts.keys()))
        return artifacts


def _infer_algo_type(hypothesis: AIHypothesis) -> str:
    desc = hypothesis.algorithm_description.lower()
    for keyword, algorithm_type in [
        ("hmac", "hmac"),
        ("rsa", "rsa"),
        ("aes", "aes"),
        ("md5", "md5"),
        ("canvas", "fingerprint"),
        ("fingerprint", "fingerprint"),
    ]:
        if keyword in desc:
            return algorithm_type
    return "custom"


def _collect_snippets(hypothesis: AIHypothesis, static_results: dict[str, StaticAnalysis]) -> str:
    snippets: list[str] = []
    for static in static_results.values():
        for candidate in static.token_candidates:
            if candidate.func_id in hypothesis.generator_func_ids and candidate.source_snippet:
                snippets.append(f"// {candidate.func_id}\n{candidate.source_snippet[:600]}")
    return "\n\n".join(snippets[:4]) or "(no source snippets found)"


def _collect_hook_data(dynamic: DynamicAnalysis | None) -> str:
    if not dynamic or not dynamic.hook_intercepts:
        return "(no dynamic hook data)"
    return json.dumps(
        [item.model_dump(mode="json") for item in dynamic.hook_intercepts[:5]],
        ensure_ascii=False,
        indent=2,
    )
