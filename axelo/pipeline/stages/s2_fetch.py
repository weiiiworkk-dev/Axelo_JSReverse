from __future__ import annotations

from axelo.models.bundle import JSBundle
from axelo.models.pipeline import StageResult


def _apply_bundle_caps(bundles: list[JSBundle], target) -> tuple[list[JSBundle], str]:
    plan = getattr(target, "execution_plan", None)
    if plan is None:
        return bundles, ""
    max_bundles = getattr(plan, "max_bundles", len(bundles))
    max_bundle_kb = getattr(plan, "max_bundle_size_kb", 1024 * 1024)
    max_total_kb = getattr(plan, "max_total_bundle_kb", 1024 * 1024)
    selected: list[JSBundle] = []
    total_kb = 0
    skipped = 0
    for bundle in bundles:
        bundle_kb = int((bundle.size_bytes or 0) / 1024)
        if bundle_kb > max_bundle_kb:
            skipped += 1
            continue
        if len(selected) >= max_bundles or total_kb + bundle_kb > max_total_kb:
            skipped += 1
            continue
        selected.append(bundle)
        total_kb += bundle_kb
    return selected, f"skipped={skipped}"


async def _download_bundle_bytes(client, url: str, *, referer: str, byte_limit: int) -> bytes | None:
    headers = {"referer": referer}
    async with client.stream("GET", url, headers=headers) as resp:
        if resp.status_code != 200:
            return None
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > byte_limit:
            return None
        parts: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > byte_limit:
                return None
            parts.append(chunk)
        return b"".join(parts)


class FetchStage:
    async def execute(self, _state, _mode, *, target, expand: bool = False):
        return StageResult(stage_name="s2_fetch", success=True, summary="fetch skipped", next_input={"bundles": [], "can_expand": False})
