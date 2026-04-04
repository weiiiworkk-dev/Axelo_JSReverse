from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import httpx
import structlog

from axelo.config import settings
from axelo.models.bundle import BundleType, JSBundle
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()

WEBPACK_PATTERN = re.compile(r"__webpack_require__|webpackChunk|webpack_modules", re.S)
VITE_PATTERN = re.compile(r"import\.meta\.env|vitePreloadCSS|__VITE_", re.S)
ROLLUP_PATTERN = re.compile(r"define\(\[", re.S)


def detect_bundle_type(code: str) -> BundleType:
    if WEBPACK_PATTERN.search(code):
        return "webpack"
    if VITE_PATTERN.search(code):
        return "vite"
    if ROLLUP_PATTERN.search(code):
        return "rollup"
    return "plain"


class FetchStage(PipelineStage):
    name = "s2_fetch"
    description = "Download JS bundles with early size guardrails."

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        target: TargetSite,
        expand: bool = False,
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        bundles_dir = session_dir / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = settings.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        max_bundles = target.execution_plan.max_bundles if target.execution_plan else 10
        if expand:
            js_urls = target.js_urls[: max(1, max_bundles * 2)]
        else:
            js_urls = target.js_urls[:4]
        if not js_urls:
            return StageResult(
                stage_name=self.name,
                success=False,
                error="No JS resource URL was discovered during crawl",
            )

        bundles: list[JSBundle] = []
        downloaded_total_bytes = 0
        single_limit = _single_bundle_cap_bytes(target, expand=expand)
        total_limit = _total_bundle_cap_bytes(target, expand=expand)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for url in js_urls:
                remaining_total = None if total_limit is None else max(0, total_limit - downloaded_total_bytes)
                if remaining_total == 0:
                    log.info("bundle_total_cap_reached", downloaded_total_bytes=downloaded_total_bytes)
                    break

                effective_limit = single_limit if remaining_total is None else min(single_limit, remaining_total)
                raw_bytes = await _download_bundle_bytes(
                    client,
                    url,
                    referer=target.url,
                    byte_limit=effective_limit,
                )
                if raw_bytes is None:
                    continue

                downloaded_total_bytes += len(raw_bytes)
                code = raw_bytes.decode("utf-8", errors="replace")
                content_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]
                bundle_id = content_hash

                cache_path = cache_dir / f"{bundle_id}.js"
                if cache_path.exists():
                    raw_path = cache_path
                    log.info("bundle_cache_hit", bundle_id=bundle_id)
                else:
                    raw_path = bundles_dir / f"{bundle_id}.raw.js"
                    raw_path.write_text(code, encoding="utf-8")
                    cache_path.write_text(code, encoding="utf-8")

                bundle_type = detect_bundle_type(code)
                bundles.append(
                    JSBundle(
                        bundle_id=bundle_id,
                        source_url=url,
                        raw_path=raw_path,
                        size_bytes=len(raw_bytes),
                        content_hash=content_hash,
                        bundle_type=bundle_type,
                    )
                )
                log.info("bundle_fetched", bundle_id=bundle_id, type=bundle_type, size=len(raw_bytes))

        if not bundles:
            return StageResult(stage_name=self.name, success=False, error="All JS bundle downloads were skipped or failed")

        bundles = _prioritize_bundles(bundles)

        options = [
            f"{bundle.bundle_id} | {bundle.bundle_type} | {bundle.size_bytes // 1024}KB | {bundle.source_url[-60:]}"
            for bundle in bundles
        ]
        options.append("analyze all")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.SELECT_OPTION,
            prompt=(
                f"Downloaded {len(bundles)} JS bundles. "
                "Choose which bundle to prioritize for deeper analysis:"
            ),
            options=options,
            default="analyze all",
            context_summary=f"Downloaded {sum(bundle.size_bytes for bundle in bundles) // 1024}KB of JS",
        )

        outcome = await mode.gate(decision, state)
        if outcome in {"analyze all", "skip"}:
            selected = bundles
        else:
            try:
                index = options.index(outcome)
                selected = [bundles[index]] if index < len(bundles) else bundles
            except ValueError:
                selected = bundles

        selected, cap_note = _apply_bundle_caps(selected, target)
        phase_label = "expanded" if expand else "initial"
        summary = f"Downloaded {len(bundles)} bundles, selected {len(selected)} for analysis ({phase_label} pass)"
        if cap_note:
            summary += f" ({cap_note})"

        meta_path = bundles_dir / "meta.json"
        meta_path.write_text(
            json.dumps([bundle.model_dump(mode="json") for bundle in selected], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"bundles_meta": meta_path},
            decisions=[decision],
            summary=summary,
            next_input={
                "bundles": selected,
                "target": target,
                "can_expand": (not expand) and len(target.js_urls) > len(js_urls),
            },
        )


def _prioritize_bundles(bundles: list[JSBundle]) -> list[JSBundle]:
    type_rank = {"webpack": 0, "vite": 1, "rollup": 2, "plain": 3, "unknown": 4}
    return sorted(
        bundles,
        key=lambda bundle: (
            type_rank.get(bundle.bundle_type, 5),
            abs(bundle.size_bytes - 180_000),
        ),
    )


def _apply_bundle_caps(bundles: list[JSBundle], target: TargetSite) -> tuple[list[JSBundle], str]:
    plan = target.execution_plan
    if plan is None:
        return bundles, ""

    capped: list[JSBundle] = []
    total_kb = 0
    skipped = 0
    for bundle in bundles:
        size_kb = max(1, bundle.size_bytes // 1024)
        if size_kb > plan.max_bundle_size_kb:
            skipped += 1
            continue
        if len(capped) >= plan.max_bundles:
            skipped += 1
            continue
        if total_kb + size_kb > plan.max_total_bundle_kb:
            skipped += 1
            continue
        capped.append(bundle)
        total_kb += size_kb

    if capped:
        note = f"bundle guardrail skipped {skipped} oversized/low-priority bundles" if skipped else ""
        return capped, note

    return bundles[: min(len(bundles), plan.max_bundles)], "bundle guardrail fallback applied"


def _single_bundle_cap_bytes(target: TargetSite, *, expand: bool) -> int:
    if not expand:
        return 256 * 1024
    plan_limit = (target.execution_plan.max_bundle_size_kb * 1024) if target.execution_plan else None
    config_limit = settings.bundle_download_byte_cap_kb * 1024
    if plan_limit is None:
        return config_limit
    return min(plan_limit, config_limit)


def _total_bundle_cap_bytes(target: TargetSite, *, expand: bool) -> int | None:
    if not expand:
        return 800 * 1024
    if target.execution_plan is None:
        return None
    return target.execution_plan.max_total_bundle_kb * 1024


async def _download_bundle_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    referer: str,
    byte_limit: int,
) -> bytes | None:
    try:
        async with client.stream("GET", url, headers={"Referer": referer}) as response:
            if response.status_code != 200:
                log.warning("bundle_fetch_failed", url=url, status=response.status_code)
                return None

            content_length = response.headers.get("Content-Length")
            try:
                declared_size = int(content_length) if content_length else None
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > byte_limit:
                log.info("bundle_skipped_content_length", url=url, content_length=declared_size, byte_limit=byte_limit)
                return None

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > byte_limit:
                    log.info("bundle_skipped_stream_limit", url=url, downloaded_bytes=total, byte_limit=byte_limit)
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception as exc:
        log.warning("bundle_fetch_error", url=url, error=str(exc))
        return None
