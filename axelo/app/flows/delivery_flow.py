from __future__ import annotations

from axelo.agents.memory_writer_agent import MemoryWriterAgent
from axelo.ai.client import AIClient
from axelo.analysis import build_signature_spec
from axelo.app.artifacts import DeliveryArtifacts
from axelo.config import settings
from axelo.pipeline.stages import CodeGenStage, VerifyStage

from ._common import artifact_map, execute_stage_with_metrics


class DeliveryFlow:
    def __init__(
        self,
        *,
        store,
        adapter_registry,
        retriever,
        mem_writer,
        verification_policy,
    ) -> None:
        self._store = store
        self._adapter_registry = adapter_registry
        self._retriever = retriever
        self._mem_writer = mem_writer
        self._verification_policy = verification_policy

    async def run(self, ctx) -> DeliveryArtifacts | None:
        if ctx.target.execution_plan and ctx.target.execution_plan.skip_codegen:
            ctx.cost.set_stage_timing("s7_codegen", 0, status="skipped", exit_reason="skip_codegen")
            ctx.cost.set_stage_timing("s8_verify", 0, status="skipped", exit_reason="skip_codegen")
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s7_codegen",
                "skipped",
                summary="Code generation disabled by compliance-aware execution plan",
            )
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s8_verify",
                "skipped",
                summary="Verification disabled by compliance-aware execution plan",
            )
            await self.write_memory(ctx)
            return DeliveryArtifacts(verified=ctx.verified)

        if ctx.analysis is None or ctx.hypothesis is None:
            ctx.result.error = "code generation prerequisites are missing"
            return None
        if ctx.ai_client is None:
            ctx.ai_client = AIClient(api_key=settings.anthropic_api_key, model=settings.model)

        codegen_stage = CodeGenStage(ctx.ai_client, ctx.cost, ctx.budget, self._retriever)
        verify_stage = VerifyStage(ctx.ai_client, ctx.cost, ctx.budget)

        ctx.target.trace = ctx.workflow.checkpoint(ctx.sid, ctx.target.trace, "s7_codegen", "running")
        ctx.state.current_stage_index = 6
        self._store.save(ctx.state)
        codegen_result = await execute_stage_with_metrics(
            ctx,
            codegen_stage,
            ctx.state,
            ctx.mode,
            hypothesis=ctx.hypothesis,
            static_results=ctx.static_results,
            target=ctx.target,
            dynamic=ctx.dynamic,
        )
        if not codegen_result.success:
            ctx.result.error = codegen_result.error
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s7_codegen",
                "failed",
                summary=ctx.result.error or "",
            )
            return None

        ctx.generated = codegen_result.next_input.get("generated")
        if ctx.generated is None:
            ctx.result.error = "code generation did not return crawler artifacts"
            return None

        if ctx.hypothesis and ctx.hypothesis.template_name:
            ctx.cost.set_route("bridge_template" if ctx.hypothesis.codegen_strategy == "js_bridge" else "family_template")
        ctx.result.output_dir = ctx.output_dir
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "s7_codegen",
            "completed",
            summary=codegen_result.summary,
            artifacts=artifact_map(codegen_result.artifacts),
        )

        ctx.target.compliance.stability_runs = self._verification_policy.stability_runs(ctx)
        max_verify_retries = self._verification_policy.max_verify_retries(ctx)
        verification = None
        verification_analysis = None
        for attempt in range(max_verify_retries):
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s8_verify",
                "running",
                summary=f"attempt {attempt + 1}/{max_verify_retries}",
            )
            ctx.state.current_stage_index = 7
            self._store.save(ctx.state)
            verify_result = await execute_stage_with_metrics(
                ctx,
                verify_stage,
                ctx.state,
                ctx.mode,
                generated=ctx.generated,
                target=ctx.target,
                hypothesis=ctx.hypothesis,
                live_verify=self._verification_policy.live_verify(ctx.target),
            )
            if not verify_result.success:
                ctx.result.error = verify_result.error
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s8_verify",
                    "failed",
                    summary=ctx.result.error or "",
                )
                return None

            ctx.generated = verify_result.next_input.get("generated", ctx.generated)
            verification = verify_result.next_input.get("verification")
            verification_analysis = verify_result.next_input.get("verification_analysis")
            ctx.verified = ctx.generated.verified
            ctx.target.trace = ctx.workflow.checkpoint(
                ctx.sid,
                ctx.target.trace,
                "s8_verify",
                "completed" if ctx.verified else "failed",
                summary=verify_result.summary,
                artifacts=artifact_map(verify_result.artifacts),
            )
            if ctx.verified:
                break
            if verification_analysis and verification_analysis.retry_strategy == "switch_to_bridge":
                ctx.hypothesis.codegen_strategy = "js_bridge"
                ctx.hypothesis.signature_spec = build_signature_spec(ctx.target, ctx.hypothesis, ctx.static_results, ctx.dynamic)
                ctx.analysis.ai_hypothesis = ctx.hypothesis
                ctx.analysis.signature_spec = ctx.hypothesis.signature_spec
                ctx.analysis.overall_confidence = ctx.hypothesis.confidence
                ctx.analysis.ready_for_codegen = (
                    ctx.hypothesis.confidence > 0.5
                    and ctx.hypothesis.signature_spec.codegen_strategy != "manual_required"
                )
                ctx.analysis.manual_review_required = ctx.hypothesis.signature_spec.codegen_strategy == "manual_required"

                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "running",
                    summary="retry with js_bridge",
                )
                ctx.state.current_stage_index = 6
                self._store.save(ctx.state)
                codegen_result = await codegen_stage.execute(
                    ctx.state,
                    ctx.mode,
                    hypothesis=ctx.hypothesis,
                    static_results=ctx.static_results,
                    target=ctx.target,
                    dynamic=ctx.dynamic,
                )
                if not codegen_result.success:
                    ctx.result.error = codegen_result.error
                    ctx.target.trace = ctx.workflow.checkpoint(
                        ctx.sid,
                        ctx.target.trace,
                        "s7_codegen",
                        "failed",
                        summary=ctx.result.error or "",
                    )
                    return None
                ctx.generated = codegen_result.next_input.get("generated", ctx.generated)
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "completed",
                    summary=f"{codegen_result.summary} (retry)",
                    artifacts=artifact_map(codegen_result.artifacts),
                )
                continue
            if verification_analysis and verification_analysis.retry_strategy == "patch_code":
                ctx.cost.set_route("ai_patch")
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "running",
                    summary="retry with patch_code",
                )
                ctx.state.current_stage_index = 6
                self._store.save(ctx.state)
                codegen_result = await execute_stage_with_metrics(
                    ctx,
                    codegen_stage,
                    ctx.state,
                    ctx.mode,
                    hypothesis=ctx.hypothesis,
                    static_results=ctx.static_results,
                    target=ctx.target,
                    dynamic=ctx.dynamic,
                )
                if not codegen_result.success:
                    ctx.result.error = codegen_result.error
                    return None
                ctx.generated = codegen_result.next_input.get("generated", ctx.generated)
                ctx.target.trace = ctx.workflow.checkpoint(
                    ctx.sid,
                    ctx.target.trace,
                    "s7_codegen",
                    "completed",
                    summary=f"{codegen_result.summary} (patch retry)",
                    artifacts=artifact_map(codegen_result.artifacts),
                )
                continue
            if verification_analysis and verification_analysis.retry_strategy == "give_up":
                break
            if verification is not None and not verification.retry_reason:
                break

        ctx.generated.verified = ctx.verified
        if ctx.verified and ctx.target.execution_plan.should_persist_adapter:
            self._adapter_registry.register(ctx.target, ctx.generated, ctx.analysis, verified=True)

        await self.write_memory(ctx)
        return DeliveryArtifacts(
            generated=ctx.generated,
            verification=verification,
            verification_analysis=verification_analysis,
            verified=ctx.verified,
        )

    async def write_memory(self, ctx) -> None:
        if ctx.analysis is None:
            return
        if ctx.ai_client is None:
            ctx.ai_client = AIClient(api_key=settings.anthropic_api_key, model=settings.model)
        mem_agent = MemoryWriterAgent(ctx.ai_client, ctx.cost, ctx.budget, writer=self._mem_writer)
        await mem_agent.write(
            session_id=ctx.sid,
            target=ctx.target,
            analysis=ctx.analysis,
            hypothesis=ctx.analysis.ai_hypothesis if ctx.analysis else None,
            cost=ctx.cost,
            verified=ctx.verified,
        )
        ctx.target.trace = ctx.workflow.checkpoint(
            ctx.sid,
            ctx.target.trace,
            "memory_write",
            "completed",
            summary="Memory updated",
        )
        ctx.state.current_stage_index = 8
        self._store.save(ctx.state)
