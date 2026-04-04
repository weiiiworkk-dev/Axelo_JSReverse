from __future__ import annotations

from axelo.models.execution import VerificationMode


def _verification_mode_value(plan) -> str:
    mode = getattr(plan, "verification_mode", "")
    return mode.value if hasattr(mode, "value") else str(mode)


def verification_was_skipped(result) -> bool:
    plan = getattr(result, "execution_plan", None)
    if plan is None:
        return False
    if bool(getattr(plan, "skip_codegen", False)):
        return True
    return _verification_mode_value(plan) == VerificationMode.NONE.value


def verification_status_markup(result) -> str:
    if getattr(result, "verified", False):
        return "[green]通过[/green]"
    if verification_was_skipped(result):
        return "[cyan]已跳过[/cyan]"
    return "[red]未通过[/red]"
