from __future__ import annotations

from axelo.agents.codegen_agent import CodeGenAgent
from axelo.config import settings
from axelo.models.codegen import GeneratedCode
from axelo.models.pipeline import StageResult


class CodeGenStage:
    def __init__(self, ai_client, cost, budget, retriever) -> None:
        self._agent = CodeGenAgent(ai_client, cost, budget, retriever=retriever)

    async def execute(self, state, _mode, *, hypothesis, static_results, target, dynamic=None):
        output_dir = settings.workspace / "sessions" / state.session_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = await self._agent.generate(target, hypothesis, static_results, dynamic, output_dir)
        crawler_path = artifacts.get("crawler_script")
        if crawler_path is None:
            return StageResult(
                stage_name="s7_codegen",
                success=False,
                error=f"produced no crawler script; artifacts={sorted(artifacts.keys())}",
            )
        reqs = []
        req_path = artifacts.get("requirements")
        if req_path and req_path.exists():
            reqs = [line.strip() for line in req_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        output_mode = "bridge" if artifacts.get("bridge_server") else "standalone"
        generated = GeneratedCode(
            session_id=state.session_id,
            output_mode=output_mode,
            crawler_script_path=crawler_path,
            bridge_server_path=artifacts.get("bridge_server"),
            manifest_path=artifacts.get("manifest"),
            crawler_deps=reqs,
        )
        return StageResult(stage_name="s7_codegen", success=True, next_input={"generated": generated})
