from __future__ import annotations

import time
from pathlib import Path


async def execute_stage_with_metrics(ctx, stage, *args, **kwargs):
    started = time.monotonic()
    result = await stage.execute(*args, **kwargs)
    ctx.cost.set_stage_timing(
        stage.name,
        int((time.monotonic() - started) * 1000),
        status="completed" if result.success else "failed",
        exit_reason=result.error or "",
    )
    return result


def artifact_map(artifacts: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in artifacts.items()}


def bundle_hashes(bundles) -> list[str]:
    hashes: list[str] = []
    for bundle in bundles:
        content_hash = getattr(bundle, "content_hash", "")
        if content_hash and content_hash not in hashes:
            hashes.append(content_hash)
    return hashes
