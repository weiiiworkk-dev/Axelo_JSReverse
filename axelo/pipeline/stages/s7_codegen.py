from __future__ import annotations

from pathlib import Path

from axelo.agents.codegen_agent import CodeGenAgent
from axelo.ai.client import AIClient
from axelo.config import settings
from axelo.cost import CostBudget, CostRecord
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.codegen import GeneratedCode
from axelo.models.pipeline import PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage


class CodeGenStage(PipelineStage):
    name = "s7_codegen"
    description = "Generate runnable crawler artifacts from the canonical AI hypothesis."

    def __init__(
        self,
        ai_client: AIClient,
        cost: CostRecord,
        budget: CostBudget,
        retriever: MemoryRetriever,
    ) -> None:
        self._ai = ai_client
        self._cost = cost
        self._budget = budget
        self._retriever = retriever

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

        codegen = CodeGenAgent(
            self._ai,
            self._cost,
            self._budget,
            retriever=self._retriever,
        )
        artifacts = await codegen.generate(
            target,
            hypothesis,
            static_results,
            dynamic,
            output_dir,
        )

        generated = GeneratedCode(
            session_id=state.session_id,
            output_mode="standalone" if not artifacts.get("bridge_server") else "bridge",
            crawler_script_path=artifacts.get("crawler_script"),
            crawler_deps=_read_requirements(artifacts.get("requirements")),
            bridge_server_path=artifacts.get("bridge_server"),
            manifest_path=artifacts.get("manifest"),
            adapter_package_path=artifacts.get("adapter_package"),
            session_state_path=Path(target.session_state.storage_state_path) if target.session_state.storage_state_path else None,
        )
        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts=artifacts,
            summary=f"Generated files: {[path.name for path in artifacts.values()]}",
            next_input={"generated": generated},
        )


def _read_requirements(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            items.append(stripped)
    return items
