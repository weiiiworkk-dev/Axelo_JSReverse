from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from axelo.models.analysis import StaticAnalysis
from axelo.models.signature import SignatureSpec
from axelo.models.target import TargetSite


class AnalysisCacheEntry(BaseModel):
    cache_key: str
    domain: str
    known_endpoint: str = ""
    goal_digest: str = ""
    target_hint_digest: str = ""
    preferred_api_base: str = ""
    output_format: str = "print"
    profile_name: str = "desktop"
    bundle_hashes: list[str] = Field(default_factory=list)
    static_results: dict[str, dict] = Field(default_factory=dict)
    scan_report: dict | None = None
    signature_family: str = "unknown"
    template_name: str = ""
    signature_spec: dict | None = None
    hits: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def static_models(self) -> dict[str, StaticAnalysis]:
        return {
            bundle_id: StaticAnalysis.model_validate(payload)
            for bundle_id, payload in self.static_results.items()
        }

    def signature_spec_model(self) -> SignatureSpec | None:
        if not self.signature_spec:
            return None
        return SignatureSpec.model_validate(self.signature_spec)


class AnalysisCache:
    def __init__(self, base_dir: Path) -> None:
        self._dir = base_dir / "analysis_cache"
        self._dir.mkdir(parents=True, exist_ok=True)

    def lookup(self, target: TargetSite, bundle_hashes: list[str]) -> AnalysisCacheEntry | None:
        domain = _domain(target.url)
        if not domain:
            return None
        path = self._path_for_domain(domain)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = [AnalysisCacheEntry.model_validate(item) for item in payload]
        except Exception:
            return None

        cache_key = self._cache_key(target, bundle_hashes)
        for entry in entries:
            if entry.cache_key != cache_key:
                continue
            entry.hits += 1
            entry.updated_at = datetime.now()
            self._save_entries(domain, entries)
            return entry
        return None

    def save(
        self,
        target: TargetSite,
        *,
        bundle_hashes: list[str],
        static_results: dict[str, StaticAnalysis],
        signature_family: str = "unknown",
        template_name: str = "",
        scan_report: dict | None = None,
        signature_spec: SignatureSpec | None = None,
    ) -> AnalysisCacheEntry | None:
        domain = _domain(target.url)
        if not domain or not bundle_hashes or not static_results:
            return None
        entry = AnalysisCacheEntry(
            cache_key=self._cache_key(target, bundle_hashes),
            domain=domain,
            known_endpoint=target.known_endpoint,
            goal_digest=_digest(target.interaction_goal),
            target_hint_digest=_digest(target.target_hint),
            preferred_api_base=_preferred_api_base(target),
            output_format=target.output_format,
            profile_name=target.browser_profile.environment_simulation.profile_name,
            bundle_hashes=sorted(bundle_hashes),
            static_results={
                bundle_id: analysis.model_dump(mode="json")
                for bundle_id, analysis in static_results.items()
            },
            scan_report=scan_report,
            signature_family=signature_family or "unknown",
            template_name=template_name,
            signature_spec=signature_spec.model_dump(mode="json") if signature_spec else None,
        )
        entries = self._load_entries(domain)
        entries = [item for item in entries if item.cache_key != entry.cache_key]
        entries.append(entry)
        self._save_entries(domain, entries[-30:])
        return entry

    def _load_entries(self, domain: str) -> list[AnalysisCacheEntry]:
        path = self._path_for_domain(domain)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [AnalysisCacheEntry.model_validate(item) for item in payload]
        except Exception:
            return []

    def _save_entries(self, domain: str, entries: list[AnalysisCacheEntry]) -> None:
        path = self._path_for_domain(domain)
        path.write_text(
            json.dumps([entry.model_dump(mode="json") for entry in entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _path_for_domain(self, domain: str) -> Path:
        slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in domain).strip("_") or "default"
        return self._dir / f"{slug}.json"

    def _cache_key(self, target: TargetSite, bundle_hashes: list[str]) -> str:
        parts = [
            _domain(target.url),
            target.known_endpoint or "",
            _digest(target.interaction_goal),
            _digest(target.target_hint),
            _preferred_api_base(target),
            target.output_format,
            target.browser_profile.environment_simulation.profile_name,
            *sorted(bundle_hashes),
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _domain(url: str) -> str:
    return urlsplit(url).netloc


def _digest(text: str) -> str:
    normalized = (text or "").strip().lower()
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _preferred_api_base(target: TargetSite) -> str:
    for request in target.target_requests:
        parsed = urlsplit(request.url)
        path = parsed.path or "/"
        if "/h5/" in path:
            prefix = path.split("/h5/", 1)[0] + "/h5"
            return f"{parsed.scheme}://{parsed.netloc}{prefix}"
    for request in target.target_requests:
        parsed = urlsplit(request.url)
        return f"{parsed.scheme}://{parsed.netloc}"
    parsed = urlsplit(target.url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
