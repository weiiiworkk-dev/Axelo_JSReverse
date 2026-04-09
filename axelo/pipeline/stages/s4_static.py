from __future__ import annotations

from axelo.models.pipeline import StageResult


def _should_skip_bundle(bundle) -> bool:
    bundle_type = (getattr(bundle, "bundle_type", "") or "").lower()
    size_bytes = int(getattr(bundle, "size_bytes", 0) or 0)
    if bundle_type == "plain" and size_bytes >= 160 * 1024:
        return True
    return False


class StaticAnalysisStage:
    def __init__(self, _ast_analyzer=None) -> None:
        pass

    async def execute(self, _state, _mode, *, bundles):
        return StageResult(stage_name="s4_static", success=True, next_input={"static_results": {}})
