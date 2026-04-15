from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from axelo.engine.models import ArtifactBundle, EngineRunResult, PreparedRun, RequirementSheet

try:
    from rich import box
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


LAVENDER = "#b6a9d6"
INK = "#f3eefc"
MUTED = "#b6a9d6"
BORDER = LAVENDER
PANEL_STYLE = "white on #000000"


@dataclass
class DashboardState:
    title: str = "Axelo Principal Runtime"
    subtitle: str = "Mission-driven crawling, reversal, and verification"
    session_id: str = ""
    target_url: str = ""
    goal: str = ""
    phase: str = "idle"
    mission_status: str = "idle"
    mission_outcome: str = "unknown"
    current_focus: str = ""
    current_uncertainty: str = ""
    evidence_count: int = 0
    hypothesis_count: int = 0
    trust_score: float = 0.0
    trust_level: str = "low"
    trust_summary: str = ""
    execution_trust_score: float = 0.0
    execution_trust_level: str = "low"
    execution_trust_summary: str = ""
    mechanism_trust_score: float = 0.0
    mechanism_trust_level: str = "low"
    mechanism_trust_summary: str = ""
    dominant_hypothesis: str = ""
    refuted_hypotheses: list[str] = field(default_factory=list)
    mechanism_blockers: list[str] = field(default_factory=list)
    branch_items: list[str] = field(default_factory=list)
    coverage_items: list[str] = field(default_factory=list)
    next_action_hint: str = ""
    evidence_delta: str = ""
    tips: list[str] = field(
        default_factory=lambda: [
            "Type a natural-language request and include a target URL when possible.",
            "The principal agent chooses the next objective from evidence gaps and mission blockers.",
            "Artifacts are persisted under workspace/sessions/AAA/AAA-000001 style site folders.",
        ]
    )
    plan_items: list[str] = field(default_factory=list)
    requirement_items: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    thought_items: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    current_prompt: str = "Startup wizard will collect crawl requirements."
    footer_hint: str = "Input > "
    wizard_step: int = 0
    wizard_total: int = 0
    wizard_answers: list[str] = field(default_factory=list)
    wizard_choices: list[str] = field(default_factory=list)
    exec_step: int = 0
    exec_max_steps: int = 0
    exec_current_tool: str = ""


class EngineTerminalUI:
    def __init__(self) -> None:
        self.console = Console() if RICH_AVAILABLE else None
        self.state = DashboardState()

    def begin_intake(self) -> None:
        self.state = DashboardState()
        self.update_context(phase="intake")
        self.state.current_prompt = "Requirement intake will collect mission target, extraction fields, and constraints."
        self.state.footer_hint = "Answer > "
        self.push_action("Requirement intake started.")

    def update_context(self, *, session_id: str = "", target_url: str = "", goal: str = "", phase: str = "") -> None:
        if session_id:
            self.state.session_id = session_id
        if target_url:
            self.state.target_url = target_url
        if goal:
            self.state.goal = goal
        if phase:
            self.state.phase = phase

    def update_principal_snapshot(
        self,
        *,
        mission_status: str = "",
        mission_outcome: str = "",
        current_focus: str = "",
        current_uncertainty: str = "",
        evidence_count: int | None = None,
        hypothesis_count: int | None = None,
        branch_items: Iterable[str] | None = None,
        coverage: dict[str, float] | None = None,
        trust_score: float | None = None,
        trust_level: str = "",
        trust_summary: str = "",
        execution_trust_score: float | None = None,
        execution_trust_level: str = "",
        execution_trust_summary: str = "",
        mechanism_trust_score: float | None = None,
        mechanism_trust_level: str = "",
        mechanism_trust_summary: str = "",
        dominant_hypothesis: str = "",
        refuted_hypotheses: Iterable[str] | None = None,
        mechanism_blockers: Iterable[str] | None = None,
        next_action_hint: str = "",
        evidence_delta: str = "",
    ) -> None:
        if mission_status:
            self.state.mission_status = mission_status
        if mission_outcome:
            self.state.mission_outcome = mission_outcome
        if current_focus:
            self.state.current_focus = current_focus
        if current_uncertainty:
            self.state.current_uncertainty = current_uncertainty
        if evidence_count is not None:
            self.state.evidence_count = evidence_count
        if hypothesis_count is not None:
            self.state.hypothesis_count = hypothesis_count
        if branch_items is not None:
            self.state.branch_items = list(branch_items)
        if coverage is not None:
            self.state.coverage_items = [f"{key}: {value:.2f}" for key, value in coverage.items()]
        if trust_score is not None:
            self.state.trust_score = trust_score
        if trust_level:
            self.state.trust_level = trust_level
        if trust_summary:
            self.state.trust_summary = trust_summary
        if execution_trust_score is not None:
            self.state.execution_trust_score = execution_trust_score
        if execution_trust_level:
            self.state.execution_trust_level = execution_trust_level
        if execution_trust_summary:
            self.state.execution_trust_summary = execution_trust_summary
        if mechanism_trust_score is not None:
            self.state.mechanism_trust_score = mechanism_trust_score
        if mechanism_trust_level:
            self.state.mechanism_trust_level = mechanism_trust_level
        if mechanism_trust_summary:
            self.state.mechanism_trust_summary = mechanism_trust_summary
        if dominant_hypothesis:
            self.state.dominant_hypothesis = dominant_hypothesis
        if refuted_hypotheses is not None:
            self.state.refuted_hypotheses = list(refuted_hypotheses)
        if mechanism_blockers is not None:
            self.state.mechanism_blockers = list(mechanism_blockers)
        if next_action_hint:
            self.state.next_action_hint = next_action_hint
        if evidence_delta:
            self.state.evidence_delta = evidence_delta

    def push_event(self, event: str) -> None:
        self.state.events.append(event)
        self.state.events = self.state.events[-10:]

    def push_action(self, action: str) -> None:
        self.state.action_items.append(action)
        self.state.action_items = self.state.action_items[-8:]
        self.push_event(action)

    def push_thought(self, thought: str) -> None:
        self.state.thought_items.append(thought)
        self.state.thought_items = self.state.thought_items[-8:]

    def set_plan(self, plan_items: Iterable[str]) -> None:
        self.state.plan_items = list(plan_items)

    def set_requirements(self, requirement_items: Iterable[str]) -> None:
        self.state.requirement_items = list(requirement_items)

    def set_wizard(self, *, step: int = 0, total: int = 0, answers: Iterable[str] | None = None) -> None:
        self.state.wizard_step = step
        self.state.wizard_total = total
        self.state.wizard_answers = list(answers or [])
        self.state.wizard_choices = []

    def set_artifacts(self, bundle: ArtifactBundle | None) -> None:
        if not bundle:
            return
        self.state.artifacts = [f"{item.category}: {Path(item.path).name}" for item in bundle.artifacts][-10:]

    def render_home(self) -> None:
        self.update_context(phase="home")
        self.set_wizard(step=0, total=0, answers=[])
        self.state.current_prompt = "Startup wizard will collect mission requirements."
        self.state.footer_hint = "Request > "
        self._render()

    def render_wizard(
        self,
        *,
        prompt_label: str,
        target_url: str = "",
        goal: str = "",
        step_index: int = 0,
        total_steps: int = 0,
        answers: Iterable[str] | None = None,
    ) -> None:
        self.update_context(phase="intake", target_url=target_url, goal=goal)
        self.set_wizard(step=step_index, total=total_steps, answers=answers)
        self.state.current_prompt = prompt_label
        self.state.footer_hint = "Answer > "
        self._render()

    def render_wizard_choices(
        self,
        *,
        prompt_label: str,
        choices: list[str],
        target_url: str = "",
        goal: str = "",
        step_index: int = 0,
        total_steps: int = 0,
        answers: Iterable[str] | None = None,
    ) -> None:
        self.update_context(phase="intake", target_url=target_url, goal=goal)
        self.state.wizard_step = step_index
        self.state.wizard_total = total_steps
        self.state.wizard_answers = list(answers or [])
        self.state.wizard_choices = list(choices)
        self.state.current_prompt = prompt_label
        self.state.footer_hint = f"Select 1-{len(choices)}, or type directly"
        self._render()

    def render_requirements(self, requirements: RequirementSheet) -> None:
        self.update_context(
            phase="requirements-ready",
            target_url=requirements.target_url,
            goal=requirements.objective,
        )
        self.set_requirements(requirements.checklist())
        self.set_wizard(step=6, total=6, answers=requirements.checklist())
        self.push_action("Requirement checklist prepared.")
        self.state.current_prompt = "Review the mission checklist and confirm to start the principal runtime."
        self.state.footer_hint = "Confirm > "
        self._render()

    def render_plan(self, prepared: PreparedRun) -> None:
        self.update_context(
            session_id=prepared.session_id,
            target_url=prepared.request.url,
            goal=prepared.request.effective_goal,
            phase="brief-ready",
        )
        if prepared.mission_brief:
            self.set_plan(prepared.mission_brief.lines_of_inquiry)
            self.push_thought(prepared.mission_brief.summary)
        else:
            self.set_plan([])
            self.push_thought(prepared.plan.summary)
        self.push_action(f"Mission brief prepared for {prepared.session_id}.")
        self.state.current_prompt = "Principal runtime finished mission framing."
        self.state.footer_hint = "Confirm > "
        self._render()

    def render_running(self, phase: str, *, step: int = 0, max_steps: int = 0, tool: str = "") -> None:
        self.update_context(phase=phase)
        if step:
            self.state.exec_step = step
        if max_steps:
            self.state.exec_max_steps = max_steps
        if tool:
            self.state.exec_current_tool = tool
        self.state.current_prompt = "Principal runtime is executing evidence-driven objectives."
        if self.state.exec_step and self.state.exec_max_steps:
            progress = f"Step {self.state.exec_step}/{self.state.exec_max_steps}"
            tool_label = f"  |  tool: {self.state.exec_current_tool}" if self.state.exec_current_tool else ""
            self.state.footer_hint = f"Running... {progress}{tool_label}"
        else:
            self.state.footer_hint = "Running..."
        self._render()

    def render_closed(self) -> None:
        self.update_context(phase="closed")
        self.state.current_prompt = "Session closed."
        self.state.footer_hint = "Restart the command to begin a new run."
        self._render()

    def render_result(self, result: EngineRunResult) -> None:
        self.update_context(phase="complete")
        self.set_artifacts(result.artifact_bundle)
        self.push_action(result.summary)
        if result.principal_state:
            self.update_principal_snapshot(
                mission_status=result.principal_state.mission.status,
                mission_outcome=result.principal_state.mission.outcome,
                current_focus=result.principal_state.mission.current_focus,
                current_uncertainty=result.principal_state.mission.current_uncertainty,
                evidence_count=len(result.principal_state.evidence),
                hypothesis_count=len(result.principal_state.hypotheses),
                branch_items=[
                    f"{branch.branch_id} [{branch.status}] score={branch.score:.2f}"
                    for branch in result.principal_state.branches[:8]
                ],
                coverage=result.principal_state.evidence_graph.coverage,
                trust_score=result.principal_state.trust.score,
                trust_level=result.principal_state.trust.level,
                trust_summary=result.principal_state.trust.summary,
                execution_trust_score=result.principal_state.trust.execution_score,
                execution_trust_level=result.principal_state.trust.execution_level,
                execution_trust_summary=result.principal_state.trust.execution_summary,
                mechanism_trust_score=result.principal_state.trust.mechanism_score,
                mechanism_trust_level=result.principal_state.trust.mechanism_level,
                mechanism_trust_summary=result.principal_state.trust.mechanism_summary,
                dominant_hypothesis=result.principal_state.mechanism.dominant_hypothesis_id,
                refuted_hypotheses=[
                    item.hypothesis_id for item in result.principal_state.hypotheses
                    if item.refute_score > item.support_score and item.refuting_evidence
                ],
                mechanism_blockers=result.principal_state.mechanism.blocking_conditions,
                next_action_hint=result.principal_state.next_action_hint,
                evidence_delta=result.principal_state.evidence_delta,
            )
            if result.principal_state.cognition_summary:
                self.push_thought(result.principal_state.cognition_summary)
        self.state.current_prompt = "Run complete. Start another session when ready."
        self.state.footer_hint = "Request > "
        self._render()

    def prompt_input(self, label: str = "Request") -> str:
        if RICH_AVAILABLE:
            return self.console.input(f"[bold {LAVENDER}]{label}[/bold {LAVENDER}]  [{INK}]>[/{INK}] ").strip()
        return input(f"{label} > ").strip()

    def prompt_confirm(self, label: str = "Execute this plan? [y/N]") -> bool:
        answer = self.prompt_input(label)
        return answer.lower() in {
            "y", "yes", "start", "go", "confirm", "execute",
            "run", "proceed", "ok", "sure", "begin", "launch",
        }

    def print_error(self, message: str) -> None:
        self.push_action(f"error: {message}")
        self.state.current_prompt = message
        self._render()

    def print_system(self, message: str) -> None:
        self.push_action(message)
        self._render()

    def _render(self) -> None:
        if not RICH_AVAILABLE:
            print("\n" + "=" * 72)
            print(self.state.title)
            print(self.state.subtitle)
            print(f"Session: {self.state.session_id or 'not started'}")
            print(f"Target: {self.state.target_url or 'not set'}")
            print(f"Goal: {self.state.goal or 'not set'}")
            print(f"Phase: {self.state.phase}")
            print("Plan:")
            for item in self.state.plan_items:
                print(f"  - {item}")
            print("Recent events:")
            for item in self.state.events:
                print(f"  - {item}")
            print("=" * 72)
            return

        if os.name == "nt":
            os.system("cls")
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        header_text = Text()
        header_text.append("AXELO", style=f"bold {LAVENDER}")
        header_text.append("  Unified Engine", style=f"bold {INK}")
        header_text.append("  principal -> constitution -> agents -> evidence -> artifacts", style=MUTED)

        layout["header"].update(
            Panel(header_text, border_style=BORDER, box=box.SQUARE, style=PANEL_STYLE)
        )
        if self.state.phase in {"intake", "requirements-ready"}:
            layout["body"].update(self._build_modal_panel())
        else:
            layout["body"].split_row(
                Layout(name="left", ratio=1),
                Layout(name="right", ratio=2),
            )
            layout["right"].split_column(
                Layout(name="top", size=11),
                Layout(name="middle", size=11),
                Layout(name="bottom"),
            )
            layout["middle"].split_row(
                Layout(name="branches"),
                Layout(name="coverage"),
                Layout(name="trust"),
            )
            layout["bottom"].split_row(
                Layout(name="actions"),
                Layout(name="thoughts"),
            )
            layout["left"].update(self._build_status_panel())
            layout["top"].update(self._build_plan_panel())
            layout["branches"].update(self._build_branch_panel())
            layout["coverage"].update(self._build_coverage_panel())
            layout["trust"].update(self._build_trust_panel())
            layout["actions"].update(self._build_action_panel())
            layout["thoughts"].update(self._build_thought_panel())
        footer_text = (
            f"[{INK}]{self.state.current_prompt}[/{INK}]\n"
            f"[bold {LAVENDER}]{self.state.footer_hint}[/]"
        )
        layout["footer"].update(
            Panel(
                footer_text,
                border_style=BORDER,
                box=box.SQUARE,
                style=PANEL_STYLE,
            )
        )
        self.console.print(layout)

    def _build_status_panel(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_row("Session", self.state.session_id or "new session")
        table.add_row("Phase", self.state.phase)
        table.add_row("Mission", self.state.mission_status or "idle")
        table.add_row("Outcome", self.state.mission_outcome or "unknown")
        table.add_row("Target", self.state.target_url or "awaiting target")
        table.add_row("Goal", self.state.goal or "awaiting request")
        table.add_row("Focus", self.state.current_focus or "establish mission context")
        table.add_row("Uncertainty", self.state.current_uncertainty or "none surfaced yet")
        table.add_row("Evidence", str(self.state.evidence_count))
        table.add_row("Hypotheses", str(self.state.hypothesis_count))
        table.add_row("Trust", f"{self.state.trust_level} ({self.state.trust_score:.2f})")
        table.add_row("Dominant", self.state.dominant_hypothesis or "not separated yet")
        table.add_row("Next", self.state.next_action_hint or "continue mission")
        table.add_row("", "")
        table.add_row("Tips", "")
        for tip in self.state.tips[:3]:
            table.add_row("", tip)
        return Panel(
            table,
            title=f"[bold {LAVENDER}]Status[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_plan_panel(self) -> Panel:
        plan_lines = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(self.state.plan_items)) or "No plan yet"
        requirement_lines = (
            "\n".join(f"- {item}" for item in self.state.requirement_items) or "No requirement checklist yet"
        )
        artifacts_lines = "\n".join(f"- {item}" for item in self.state.artifacts[-5:]) or "No artifacts yet"
        content = (
            f"[bold {LAVENDER}]Requirement checklist[/bold {LAVENDER}]\n{requirement_lines}\n\n"
            f"[bold {LAVENDER}]Execution graph[/bold {LAVENDER}]\n{plan_lines}\n\n"
            f"[bold {LAVENDER}]Recent artifacts[/bold {LAVENDER}]\n{artifacts_lines}"
        )
        return Panel(
            content,
            title=f"[bold {LAVENDER}]Mission View[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_action_panel(self) -> Panel:
        actions = "\n".join(f"- {item}" for item in self.state.action_items) or "No actions yet"
        return Panel(
            actions,
            title=f"[bold {LAVENDER}]Action Trace[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_thought_panel(self) -> Panel:
        notes = "\n".join(f"- {item}" for item in self.state.thought_items[-4:]) or "- No cognitive updates yet"
        thoughts = (
            f"[bold {LAVENDER}]Current goal[/bold {LAVENDER}]\n{self.state.goal or 'awaiting request'}\n\n"
            f"[bold {LAVENDER}]Current uncertainty[/bold {LAVENDER}]\n{self.state.current_uncertainty or 'none surfaced yet'}\n\n"
            f"[bold {LAVENDER}]Why this next step[/bold {LAVENDER}]\n{self.state.next_action_hint or 'continue current branch'}\n\n"
            f"[bold {LAVENDER}]Evidence delta[/bold {LAVENDER}]\n{self.state.evidence_delta or 'no evidence delta yet'}\n\n"
            f"[bold {LAVENDER}]Mechanism blockers[/bold {LAVENDER}]\n"
            f"{chr(10).join(f'- {item}' for item in self.state.mechanism_blockers[:4]) if self.state.mechanism_blockers else '- none'}\n\n"
            f"[bold {LAVENDER}]Recent cognition[/bold {LAVENDER}]\n{notes}"
        )
        return Panel(
            thoughts,
            title=f"[bold {LAVENDER}]Cognition[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_branch_panel(self) -> Panel:
        body = "\n".join(f"- {item}" for item in self.state.branch_items) or "No branch activity yet"
        return Panel(
            body,
            title=f"[bold {LAVENDER}]Branch Tree[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_coverage_panel(self) -> Panel:
        body = "\n".join(f"- {item}" for item in self.state.coverage_items) or "No coverage yet"
        return Panel(
            body,
            title=f"[bold {LAVENDER}]Evidence Coverage[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_trust_panel(self) -> Panel:
        body = (
            f"[bold {LAVENDER}]Overall[/bold {LAVENDER}]\n{self.state.trust_level} ({self.state.trust_score:.2f})\n\n"
            f"[bold {LAVENDER}]Execution[/bold {LAVENDER}]\n"
            f"{self.state.execution_trust_level} ({self.state.execution_trust_score:.2f})\n"
            f"{self.state.execution_trust_summary or 'Execution trust not scored yet.'}\n\n"
            f"[bold {LAVENDER}]Mechanism[/bold {LAVENDER}]\n"
            f"{self.state.mechanism_trust_level} ({self.state.mechanism_trust_score:.2f})\n"
            f"{self.state.mechanism_trust_summary or 'Mechanism trust not scored yet.'}"
        )
        return Panel(
            body,
            title=f"[bold {LAVENDER}]Trust Level[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    # ── AI Intake Chat display ────────────────────────────────────────────────

    def render_intake_chat(
        self,
        contract: Any,
        chat_history: list[dict],
        readiness: Any,
        *,
        waiting: bool = False,
    ) -> None:
        """Render the three-panel AI intake chat view."""
        if not RICH_AVAILABLE:
            print("\n" + "=" * 72)
            print("AXELO  AI Intake — describe your goal")
            url = getattr(contract, "target_url", "") or ""
            obj = getattr(contract, "objective", "") or ""
            conf = getattr(readiness, "confidence", 0.0) or 0.0
            print(f"Target: {url or '(not set)'}  Objective: {obj or '(not set)'}")
            print(f"Confidence: {int(conf * 100)}%")
            for turn in chat_history[-6:]:
                role = turn.get("role", "?")
                content = (turn.get("content") or "")[:120]
                print(f"  [{role}] {content}")
            if waiting:
                print("  [AI thinking...]")
            print("=" * 72)
            return

        if os.name == "nt":
            os.system("cls")
        else:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=4),
        )

        header_text = Text()
        header_text.append("AXELO", style=f"bold {LAVENDER}")
        header_text.append("  AI 需求助手", style=f"bold {INK}")
        header_text.append(
            "  描述你的目标 — 准备好后输入 'start' 开始，'quit' 退出",
            style=MUTED,
        )
        layout["header"].update(
            Panel(header_text, border_style=BORDER, box=box.SQUARE, style=PANEL_STYLE)
        )

        layout["body"].split_row(
            Layout(name="contract", ratio=2),
            Layout(name="chat", ratio=3),
        )
        layout["contract"].update(self._build_intake_contract_panel(contract))
        layout["chat"].update(self._build_intake_chat_panel(chat_history, waiting))
        layout["footer"].update(self._build_intake_footer_panel(readiness))

        self.console.print(layout)

    def _build_intake_contract_panel(self, contract: Any) -> Panel:
        """Build the left-panel mission contract display for intake phase."""
        target_url = getattr(contract, "target_url", "") or ""
        objective = getattr(contract, "objective", "") or ""
        objective_type = getattr(contract, "objective_type", "") or ""
        item_limit = getattr(contract, "item_limit", 50) or 50
        contract_version = getattr(contract, "contract_version", 0) or 0
        assumptions = getattr(contract, "assumptions", []) or []
        constraints = getattr(contract, "constraints", []) or []
        requested_fields = getattr(contract, "requested_fields", []) or []
        readiness = getattr(contract, "readiness_assessment", None)
        conf = getattr(readiness, "confidence", 0.0) if readiness else 0.0
        blocking_gaps = getattr(readiness, "blocking_gaps", []) if readiness else []
        missing_info = getattr(readiness, "missing_info", []) if readiness else []

        # Confidence bar
        bar_len = 20
        filled = round(conf * bar_len)
        conf_bar = f"[bold green]{'█' * filled}[/bold green][dim]{'░' * (bar_len - filled)}[/dim]"
        conf_pct = f"{int(conf * 100)}%"
        if conf >= 0.75:
            conf_color = "bold green"
        elif conf >= 0.50:
            conf_color = "bold yellow"
        else:
            conf_color = "bold red"

        lines = []
        lines.append(
            f"[{LAVENDER}]Contract v{contract_version}[/{LAVENDER}]  "
            f"[{conf_color}]{conf_pct}[/{conf_color}]  {conf_bar}"
        )
        lines.append("")

        # Target
        lines.append(f"[bold {LAVENDER}]TARGET[/bold {LAVENDER}]")
        lines.append(f"  {target_url or '[dim](not set)[/dim]'}")
        if objective_type:
            lines.append(f"  Type: {objective_type}")
        lines.append("")

        # Objective
        lines.append(f"[bold {LAVENDER}]OBJECTIVE[/bold {LAVENDER}]")
        if objective:
            # Wrap long objectives
            for i in range(0, len(objective), 38):
                lines.append(f"  {objective[i:i+38]}")
        else:
            lines.append("  [dim](not set)[/dim]")
        lines.append(f"  Limit: {item_limit} items")
        lines.append("")

        # Fields
        if requested_fields:
            lines.append(f"[bold {LAVENDER}]FIELDS ({len(requested_fields)})[/bold {LAVENDER}]")
            for fs in requested_fields[:6]:
                name = getattr(fs, "field_name", "?") or "?"
                dtype = getattr(fs, "data_type", "string") or "string"
                prio = getattr(fs, "priority", 1) or 1
                marker = "[green]*[/green]" if prio == 1 else "[dim]~[/dim]"
                lines.append(f"  {marker} {name:<16} {dtype}")
            if len(requested_fields) > 6:
                lines.append(f"  [dim]... +{len(requested_fields)-6} more[/dim]")
            lines.append("")

        # Assumptions
        if assumptions:
            lines.append(f"[bold {LAVENDER}]ASSUMED[/bold {LAVENDER}]")
            for a in assumptions[:3]:
                lines.append(f"  [dim]{a[:42]}[/dim]")
            lines.append("")

        # Constraints
        if constraints:
            lines.append(f"[bold {LAVENDER}]CONSTRAINTS[/bold {LAVENDER}]")
            for c in constraints[:3]:
                lines.append(f"  - {c[:42]}")
            lines.append("")

        # Still needed
        all_gaps = list(blocking_gaps) + [g for g in missing_info if g not in blocking_gaps]
        if all_gaps:
            lines.append(f"[bold yellow]STILL NEEDED[/bold yellow]")
            for g in all_gaps[:4]:
                lines.append(f"  [yellow]- {g[:42]}[/yellow]")
        else:
            lines.append(f"[bold green]READY TO START[/bold green]")

        return Panel(
            "\n".join(lines),
            title=f"[bold {LAVENDER}]Mission Contract[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_intake_chat_panel(self, history: list[dict], waiting: bool) -> Panel:
        """Build the right-panel chat history display."""
        lines = []
        # Show last N turns that fit
        visible = history[-12:]
        for turn in visible:
            role = turn.get("role", "?")
            content = (turn.get("content") or "").strip()
            if role == "user":
                lines.append(f"[bold {INK}]You[/bold {INK}]")
                # Wrap content
                for i in range(0, min(len(content), 200), 60):
                    lines.append(f"  {content[i:i+60]}")
                lines.append("")
            else:
                lines.append(f"[bold {LAVENDER}]Axelo[/bold {LAVENDER}]")
                for i in range(0, min(len(content), 400), 60):
                    lines.append(f"  {content[i:i+60]}")
                lines.append("")
        if waiting:
            lines.append(f"[bold {LAVENDER}]Axelo[/bold {LAVENDER}]")
            lines.append(f"  [dim italic]正在思考...[/dim italic]")

        if not lines:
            lines = [
                f"[dim]告诉 Axelo 你想爬取什么，或者想逆向分析哪个网站。[/dim]",
                "",
                f"[dim]示例：[/dim]",
                f"[dim]  '从 amazon.com 获取 iPhone 15 商品列表'[/dim]",
                f"[dim]  '抓取 linkedin.com 上的招聘信息'[/dim]",
                f"[dim]  '逆向分析 example.com 的搜索 API'[/dim]",
            ]

        return Panel(
            "\n".join(lines),
            title=f"[bold {LAVENDER}]对话[/bold {LAVENDER}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_intake_footer_panel(self, readiness: Any) -> Panel:
        """Build the footer panel with readiness bar and input hint."""
        conf = getattr(readiness, "confidence", 0.0) if readiness else 0.0
        is_ready = getattr(readiness, "is_ready", False) if readiness else False
        suggestions = getattr(readiness, "suggestions", []) if readiness else []

        bar_len = 30
        filled = round(conf * bar_len)
        blocking_gaps = getattr(readiness, "blocking_gaps", []) if readiness else []
        if is_ready:
            bar_style = "bold green"
            status = "[bold green]就绪 — 输入 'start' 开始任务[/bold green]"
        elif conf >= 0.50:
            bar_style = "bold yellow"
            status = "[yellow]讨论中...[/yellow]"
        else:
            bar_style = "bold red"
            status = "[dim]需要更多信息[/dim]"

        conf_bar = f"[{bar_style}]{'█' * filled}[/{bar_style}][dim]{'░' * (bar_len - filled)}[/dim]"
        readiness_line = f"就绪度: [{bar_style}]{int(conf*100)}%[/{bar_style}]  {conf_bar}  {status}"

        # Show first blocking gap if present (hard gate, not just a suggestion)
        hint = ""
        if blocking_gaps:
            hint = f"\n[bold red]✗[/bold red] [dim]{blocking_gaps[0][:90]}[/dim]"
        elif suggestions:
            hint = f"\n[dim italic]{suggestions[0][:90]}[/dim italic]"

        # No "Chat >" here — the actual input prompt comes from prompt_input() below the layout
        return Panel(
            f"{readiness_line}{hint}",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
        )

    def _build_modal_panel(self) -> Panel:
        progress = "Step pending"
        if self.state.wizard_total:
            progress = f"Step {self.state.wizard_step}/{self.state.wizard_total}"

        answers = "\n".join(f"  - {item}" for item in self.state.wizard_answers) or "  - No answers captured yet"

        if self.state.wizard_choices:
            # ── Choice mode ──────────────────────────────────────────────
            n = len(self.state.wizard_choices)
            option_lines: list[str] = []
            for i, label in enumerate(self.state.wizard_choices):
                num = i + 1
                if i < n - 1:
                    option_lines.append(
                        f"  [bold {LAVENDER}]{num}[/bold {LAVENDER}]  {label}"
                    )
                else:
                    # Last option = free-text sentinel — visually separated
                    option_lines.append(f"  [dim]{'─' * 40}[/dim]")
                    option_lines.append(
                        f"  [bold {LAVENDER}]{num}[/bold {LAVENDER}]  [dim italic]{label}[/dim italic]"
                    )
            choices_block = "\n".join(option_lines)
            modal_body = (
                f"[bold {LAVENDER}]{progress}[/bold {LAVENDER}]\n"
                f"[bold {LAVENDER}]{self.state.current_prompt}[/bold {LAVENDER}]\n\n"
                f"[bold {LAVENDER}]Options[/bold {LAVENDER}]\n{choices_block}\n\n"
                f"[bold {LAVENDER}]Collected answers[/bold {LAVENDER}]\n{answers}"
            )
        else:
            # ── Free-text mode (Step 1 / confirm review) ─────────────────
            checklist = (
                "\n".join(f"  - {item}" for item in self.state.requirement_items)
                or "  - Requirement checklist will appear here"
            )
            modal_body = (
                f"[bold {LAVENDER}]{progress}[/bold {LAVENDER}]\n"
                f"[bold {LAVENDER}]Current question[/bold {LAVENDER}]\n{self.state.current_prompt}\n\n"
                f"[bold {LAVENDER}]Collected answers[/bold {LAVENDER}]\n{answers}\n\n"
                f"[bold {LAVENDER}]Checklist preview[/bold {LAVENDER}]\n{checklist}"
            )

        return Panel(
            modal_body,
            title=f"[bold {LAVENDER}]Requirement Intake[/bold {LAVENDER}]",
            subtitle=f"[{MUTED}]Lavender modal workflow[/{MUTED}]",
            border_style=BORDER,
            box=box.SQUARE,
            style=PANEL_STYLE,
            padding=(1, 3),
        )
