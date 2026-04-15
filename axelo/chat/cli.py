"""
Axelo Chat CLI — AI-mediated intake + mission execution.

Pre-execution:
  Left   → Mission Contract panel (live-updating as AI processes chat)
  Right  → Chat history (user ↔ AI discussion)
  Footer → Readiness gauge + input

During execution:
  Existing principal runtime display (EngineTerminalUI full layout)
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import structlog

from axelo.engine.runtime import UnifiedEngine
from axelo.engine.ui import EngineTerminalUI
from axelo.engine.models import RequirementSheet

# Import tools for side-effect registration.
from axelo import tools as _registered_tools  # noqa: F401

log = structlog.get_logger()

# Words that mean "start the mission now"
_START_WORDS = {
    "start", "begin", "go", "run", "execute", "launch", "proceed",
    "开始", "启动", "执行", "出发", "跑", "ok", "yes", "y",
}

# Words that exit the CLI
_EXIT_WORDS = {"quit", "exit", "/quit", "/exit", "q", "退出", "exit()"}


class AxeloChatCLI:
    """Mission-driven principal runtime CLI — AI chat intake."""

    def __init__(self) -> None:
        self.ui = EngineTerminalUI()
        self.engine = UnifiedEngine()
        self._running = False
        self.engine.set_thinking_callback(self._on_thinking)
        self.engine.set_event_callback(self._on_event)

    # ── Engine event callbacks ────────────────────────────────────────────────

    def _on_thinking(self, thinking: str) -> None:
        self.ui.push_thought(thinking)
        tool = ""
        if thinking.startswith("Running tool: "):
            tool = thinking[len("Running tool: "):]
        self.ui.render_running("framing", tool=tool)

    def _on_event(self, kind: str, message: str, payload: dict) -> None:
        phase = {
            "mission": "brief-ready",
            "dispatch": "running",
            "complete": "complete",
        }.get(kind, "running")
        self.ui.update_principal_snapshot(
            mission_status=str(payload.get("mission_status") or ""),
            mission_outcome=str(payload.get("mission_outcome") or ""),
            current_focus=str(payload.get("current_focus") or ""),
            current_uncertainty=str(payload.get("current_uncertainty") or ""),
            evidence_count=payload.get("evidence_count") if "evidence_count" in payload else None,
            hypothesis_count=payload.get("hypothesis_count") if "hypothesis_count" in payload else None,
            branch_items=payload.get("branch_tree"),
            coverage=payload.get("coverage"),
            trust_score=payload.get("trust_score") if "trust_score" in payload else None,
            trust_level=str(payload.get("trust_level") or ""),
            trust_summary=str(payload.get("trust_summary") or ""),
            execution_trust_score=payload.get("execution_trust_score") if "execution_trust_score" in payload else None,
            execution_trust_level=str(payload.get("execution_trust_level") or ""),
            execution_trust_summary=str(payload.get("execution_trust_summary") or ""),
            mechanism_trust_score=payload.get("mechanism_trust_score") if "mechanism_trust_score" in payload else None,
            mechanism_trust_level=str(payload.get("mechanism_trust_level") or ""),
            mechanism_trust_summary=str(payload.get("mechanism_trust_summary") or ""),
            dominant_hypothesis=str(payload.get("dominant_hypothesis") or ""),
            refuted_hypotheses=payload.get("refuted_hypotheses"),
            mechanism_blockers=payload.get("mechanism_blockers"),
            next_action_hint=str(payload.get("next_action_hint") or ""),
            evidence_delta=str(payload.get("evidence_delta") or ""),
        )
        self.ui.push_action(message)
        self.ui.render_running(
            phase,
            step=int(payload.get("step") or 0),
            max_steps=int(payload.get("max_steps") or 0),
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True

        while self._running:
            try:
                self.ui.begin_intake()

                # AI chat intake — returns a MissionContract or None (user quit)
                contract = await self._run_ai_intake()
                if contract is None:
                    break

                # Convert to RequirementSheet for engine backwards compat
                requirements = RequirementSheet(**contract.to_requirement_sheet_kwargs())

                prepared = await self.engine.plan_request(
                    prompt=requirements.to_prompt(),
                    url=requirements.target_url,
                    goal=requirements.objective,
                    metadata={
                        "requirements": requirements.to_metadata(),
                        "contract": contract.model_dump(),
                    },
                )
                # Attach live MissionContract so _populate_field_evidence() works in CLI mode
                prepared.contract = contract

                self.ui.render_plan(prepared)

                if not self.ui.prompt_confirm("确认并开始执行? [y/N]"):
                    self.ui.push_action("已取消执行，返回需求收集。")
                    continue

                result = await self.engine.execute_prepared(prepared)
                self.ui.render_result(result)

                if not self.ui.prompt_confirm("开始新任务? [y/N]"):
                    break

            except KeyboardInterrupt:
                break
            except EOFError:
                break
            except Exception as exc:
                log.error("cli_error", error=str(exc))
                self.ui.print_error(str(exc))

        self.ui.push_action("Session closed.")
        self.ui.render_closed()

    # ── AI Chat Intake ────────────────────────────────────────────────────────

    async def _run_ai_intake(self):
        """
        AI-mediated intake loop.
        Shows left=contract, right=chat panels.
        Returns MissionContract when readiness >= 0.75 and user says 'start'.
        Returns None if user quits.
        """
        from axelo.models.contracts import MissionContract
        from axelo.engine.principal import IntakeAIProcessor

        intake = IntakeAIProcessor()
        contract = MissionContract()
        history: list[dict] = []

        # Initial render
        self.ui.render_intake_chat(contract, history, contract.readiness_assessment)

        while True:
            try:
                raw = self.ui.prompt_input("输入")
            except (EOFError, KeyboardInterrupt):
                return None

            text = raw.strip()
            if not text:
                continue

            # Exit
            if text.lower() in _EXIT_WORDS:
                return None

            # Start command
            if text.lower() in _START_WORDS:
                readiness = contract.readiness_assessment
                if readiness.is_ready:
                    return contract
                else:
                    gaps = readiness.blocking_gaps or ["需求信息不完整"]
                    self.ui.render_intake_chat(contract, history, readiness)
                    self.ui.print_error(
                        "尚未就绪: " + "; ".join(gaps[:2])
                    )
                    continue

            # Add user message to history
            history.append({"role": "user", "content": text})

            # Show waiting state (AI thinking)
            self.ui.render_intake_chat(contract, history, contract.readiness_assessment, waiting=True)

            # Call AI
            try:
                result = await intake.process_message(text, contract, history)
                contract = result["updated_contract"]
                ai_reply = result["ai_reply"]
                history.append({"role": "assistant", "content": ai_reply})
            except Exception as exc:
                log.warning("intake_ai_error", error=str(exc))
                history.append({
                    "role": "assistant",
                    "content": f"[连接 AI 出错: {exc}，请检查网络后重试。]",
                })

            # Re-render with updated contract and AI reply
            self.ui.render_intake_chat(contract, history, contract.readiness_assessment)

            # Auto-prompt if ready
            readiness = contract.readiness_assessment
            if readiness.is_ready and not any(
                m.get("content", "").lower() in {s.lower() for s in _START_WORDS}
                for m in history[-3:]
                if m.get("role") == "assistant"
            ):
                pass  # AI reply already prompted user to start

    # ── Non-interactive mode (URL + goal as args) ─────────────────────────────

    async def _run_non_interactive(self, url: str, goal: str) -> None:
        prepared = await self.engine.plan_request(prompt=goal, url=url, goal=goal)
        self.ui.render_plan(prepared)
        result = await self.engine.execute_prepared(prepared)
        self.ui.render_result(result)
        self.ui.print_system(result.summary)


async def main() -> None:
    cli = AxeloChatCLI()
    await cli.start()


def main_sync() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
