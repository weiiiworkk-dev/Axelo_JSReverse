from __future__ import annotations
from axelo.modes.base import ModeController
from axelo.modes.interactive import InteractiveMode
from axelo.modes.full_auto import AutoMode
from axelo.modes.full_manual import ManualMode

_REGISTRY: dict[str, type[ModeController]] = {
    "interactive": InteractiveMode,
    "auto": AutoMode,
    "manual": ManualMode,
}


def create_mode(name: str) -> ModeController:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知模式: {name!r}，可选: {list(_REGISTRY)}")
    return cls()


def available_modes() -> list[str]:
    return list(_REGISTRY)
