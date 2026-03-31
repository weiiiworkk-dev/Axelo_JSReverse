from __future__ import annotations
import hashlib
import re
from pathlib import Path
import httpx
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite
from axelo.models.bundle import JSBundle, BundleType
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()

# webpack runtime 特征
WEBPACK_PATTERN = re.compile(r'__webpack_require__|webpackChunk|webpack_modules', re.S)
VITE_PATTERN = re.compile(r'import\.meta\.env|vitePreloadCSS|__VITE_', re.S)
ROLLUP_PATTERN = re.compile(r'define\(\[', re.S)


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
    description = "下载JS Bundle，检测类型，准备去混淆"

    async def run(self, state: PipelineState, mode: ModeController, target: TargetSite, **_) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        bundles_dir = session_dir / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = settings.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 仅下载前10个JS文件（优先级：bundle大小，主文件优先）
        js_urls = target.js_urls[:10]
        if not js_urls:
            return StageResult(
                stage_name=self.name, success=False,
                error="未发现任何JS资源URL，请检查爬取阶段",
            )

        bundles: list[JSBundle] = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for url in js_urls:
                try:
                    resp = await client.get(url, headers={"Referer": target.url})
                    if resp.status_code != 200:
                        log.warning("bundle_fetch_failed", url=url, status=resp.status_code)
                        continue
                    code = resp.text
                except Exception as e:
                    log.warning("bundle_fetch_error", url=url, error=str(e))
                    continue

                content_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
                bundle_id = content_hash

                # 检查缓存
                cache_path = cache_dir / f"{bundle_id}.js"
                if cache_path.exists():
                    raw_path = cache_path
                    log.info("bundle_cache_hit", bundle_id=bundle_id)
                else:
                    raw_path = bundles_dir / f"{bundle_id}.raw.js"
                    raw_path.write_text(code, encoding="utf-8")
                    cache_path.write_text(code, encoding="utf-8")

                bundle_type = detect_bundle_type(code)
                bundles.append(JSBundle(
                    bundle_id=bundle_id,
                    source_url=url,
                    raw_path=raw_path,
                    size_bytes=len(code),
                    content_hash=content_hash,
                    bundle_type=bundle_type,
                ))
                log.info("bundle_fetched", bundle_id=bundle_id, type=bundle_type, size=len(code))

        if not bundles:
            return StageResult(stage_name=self.name, success=False, error="所有JS文件下载失败")

        # 决策：优先分析哪些 bundle
        options = [
            f"{b.bundle_id} | {b.bundle_type} | {b.size_bytes//1024}KB | {b.source_url[-60:]}"
            for b in bundles
        ]
        options.append("全部分析")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.SELECT_OPTION,
            prompt=f"下载了 {len(bundles)} 个JS文件，选择优先深度分析的bundle（webpack bundle 通常是主要目标）：",
            options=options,
            default="全部分析",
            context_summary=f"总计 {sum(b.size_bytes for b in bundles)//1024}KB JS代码",
        )

        outcome = await mode.gate(decision, state)

        # 根据选择过滤 bundle
        if outcome == "全部分析" or outcome == "skip":
            selected = bundles
        else:
            try:
                idx = options.index(outcome)
                selected = [bundles[idx]] if idx < len(bundles) else bundles
            except ValueError:
                selected = bundles

        # 序列化 bundles 元数据
        meta_path = session_dir / "bundles" / "meta.json"
        meta_path.write_text(
            __import__("json").dumps(
                [b.model_dump(mode="json") for b in selected], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"bundles_meta": meta_path},
            decisions=[decision],
            summary=f"下载 {len(bundles)} 个bundle，选择分析 {len(selected)} 个",
            next_input={"bundles": selected, "target": target},
        )
