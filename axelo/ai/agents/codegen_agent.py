from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .base import BaseAgent
from .codegen_services import (
    PROMPTS_DIR,
    AICodegenService,
    ArtifactWriter,
    GroundingService,
    TemplateCodegenService,
    _preferred_api_base,
    _repair_generated_code_for_target,
    _render_base_bridge_template,
    _render_base_crawler_template,
    _render_template_codegen,
    _template_is_ready,
)
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.target import TargetSite


class CodeGenAgent(BaseAgent):
    role = "codegen"
    default_model = "deepseek-chat"

    def __init__(self, *args, retriever: MemoryRetriever, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
        self._grounding = GroundingService()
        self._templates = TemplateCodegenService()
        self._ai_codegen = AICodegenService(agent=self, jinja=self._jinja, grounding=self._grounding)
        self._writer = ArtifactWriter(grounding=self._grounding)

    async def generate(
        self,
        target: TargetSite,
        hypothesis: AIHypothesis,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        output_dir: Path,
    ) -> dict[str, Path]:
        templates = self._retriever.get_all_templates()
        selected_template, template_code = self._templates.select_template(hypothesis, templates)

        if self._templates.supports_builtin(hypothesis):
            output = self._templates.render_builtin(target, hypothesis, dynamic=dynamic)
        elif hypothesis.template_name and selected_template is not None and self._templates.is_ready(hypothesis, selected_template):
            output = self._templates.render(selected_template, target, hypothesis, dynamic=dynamic)
        else:
            output = await self._ai_codegen.generate(
                target=target,
                hypothesis=hypothesis,
                static_results=static_results,
                dynamic=dynamic,
                template_code=template_code,
            )

        return self._writer.write(
            output=output,
            hypothesis=hypothesis,
            target=target,
            dynamic=dynamic,
            output_dir=output_dir,
        )


__all__ = [
    "CodeGenAgent",
    "_preferred_api_base",
    "_repair_generated_code_for_target",
    "_render_base_bridge_template",
    "_render_base_crawler_template",
    "_render_template_codegen",
    "_template_is_ready",
]
