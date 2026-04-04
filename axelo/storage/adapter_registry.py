from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "default"


def _goal_digest(goal: str) -> str:
    return hashlib.sha1(goal.strip().lower().encode("utf-8")).hexdigest()[:16]


def _target_hint_digest(target_hint: str) -> str:
    normalized = target_hint.strip().lower()
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


class AdapterRecord(BaseModel):
    registry_key: str
    domain: str
    goal_digest: str
    target_hint_digest: str = ""
    known_endpoint: str = ""
    preferred_api_base: str = ""
    output_format: str = "print"
    profile_name: str = "desktop"
    verified: bool = False
    output_mode: str = "standalone"
    crawler_script_path: str = ""
    bridge_server_path: str = ""
    manifest_path: str = ""
    session_state_path: str = ""
    source_session_id: str = ""
    signature_spec: dict | None = None
    notes: list[str] = Field(default_factory=list)
    use_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_used_at: datetime | None = None


class AdapterMaterialization(BaseModel):
    crawler_script_path: Path | None = None
    bridge_server_path: Path | None = None
    manifest_path: Path | None = None
    session_state_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


class AdapterRegistry:
    def __init__(self, base_dir: Path) -> None:
        self._dir = base_dir / "adapter_registry"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _registry_path(self, domain: str) -> Path:
        return self._dir / f"{_slugify(domain)}.json"

    def _load(self, domain: str) -> list[AdapterRecord]:
        path = self._registry_path(domain)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [AdapterRecord.model_validate(item) for item in payload]
        except Exception:
            return []

    def _save(self, domain: str, records: list[AdapterRecord]) -> None:
        path = self._registry_path(domain)
        path.write_text(
            json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def lookup(self, target: TargetSite) -> AdapterRecord | None:
        domain = urlparse(target.url).netloc
        candidates = self._load(domain)
        if not candidates:
            return None

        exact_goal = _goal_digest(target.interaction_goal)
        target_hint_digest = _target_hint_digest(target.target_hint)
        preferred_api_base = _preferred_api_base(target)
        profile_name = target.browser_profile.environment_simulation.profile_name
        best_score = -1
        best: AdapterRecord | None = None

        for record in candidates:
            if not record.verified:
                continue
            score = 0
            if record.goal_digest == exact_goal:
                score += 4
            if record.target_hint_digest and record.target_hint_digest == target_hint_digest:
                score += 2
            if target.known_endpoint and record.known_endpoint and record.known_endpoint == target.known_endpoint:
                score += 3
            if record.preferred_api_base and record.preferred_api_base == preferred_api_base:
                score += 2
            if record.output_format == target.output_format:
                score += 1
            if record.profile_name == profile_name:
                score += 1
            score += min(record.use_count, 5)
            if self._artifacts_exist(record):
                score += 2
            if score > best_score:
                best_score = score
                best = record

        return best if best_score >= 4 else None

    def touch(self, record: AdapterRecord) -> None:
        records = self._load(record.domain)
        updated: list[AdapterRecord] = []
        for item in records:
            if item.registry_key == record.registry_key:
                clone = item.model_copy(deep=True)
                clone.use_count += 1
                clone.last_used_at = datetime.now()
                clone.updated_at = datetime.now()
                updated.append(clone)
            else:
                updated.append(item)
        self._save(record.domain, updated)

    def register(self, target: TargetSite, generated: GeneratedCode, analysis: AnalysisResult | None, verified: bool) -> AdapterRecord | None:
        domain = urlparse(target.url).netloc
        if not domain or generated.crawler_script_path is None or not generated.crawler_script_path.exists():
            return None

        registry_key = f"{_slugify(domain)}-{target.known_endpoint or 'default'}-{_goal_digest(target.interaction_goal)}"
        record = AdapterRecord(
            registry_key=registry_key,
            domain=domain,
            goal_digest=_goal_digest(target.interaction_goal),
            target_hint_digest=_target_hint_digest(target.target_hint),
            known_endpoint=target.known_endpoint,
            preferred_api_base=_preferred_api_base(target),
            output_format=target.output_format,
            profile_name=target.browser_profile.environment_simulation.profile_name,
            verified=verified,
            output_mode=generated.output_mode,
            crawler_script_path=str(generated.crawler_script_path),
            bridge_server_path=str(generated.bridge_server_path) if generated.bridge_server_path else "",
            manifest_path=str(generated.manifest_path) if generated.manifest_path else "",
            session_state_path=str(generated.session_state_path) if generated.session_state_path else "",
            source_session_id=target.session_id,
            signature_spec=analysis.signature_spec.model_dump(mode="json") if analysis and analysis.signature_spec else None,
            notes=[f"url={target.url}"],
            use_count=1,
        )

        records = [item for item in self._load(domain) if item.registry_key != registry_key]
        records.append(record)
        self._save(domain, records[-20:])
        return record

    def materialize(self, record: AdapterRecord, output_dir: Path) -> AdapterMaterialization:
        output_dir.mkdir(parents=True, exist_ok=True)
        materialized = AdapterMaterialization()
        materialized.crawler_script_path = self._copy_if_exists(Path(record.crawler_script_path), output_dir)
        materialized.bridge_server_path = self._copy_if_exists(Path(record.bridge_server_path), output_dir) if record.bridge_server_path else None
        materialized.manifest_path = self._copy_if_exists(Path(record.manifest_path), output_dir) if record.manifest_path else None
        materialized.session_state_path = (
            self._copy_if_exists(Path(record.session_state_path), output_dir) if record.session_state_path else None
        )
        self.touch(record)
        return materialized

    def _artifacts_exist(self, record: AdapterRecord) -> bool:
        return bool(record.crawler_script_path) and Path(record.crawler_script_path).exists()

    def _copy_if_exists(self, source: Path, output_dir: Path) -> Path | None:
        if not source.exists():
            return None
        destination = output_dir / source.name
        shutil.copy2(source, destination)
        return destination


def _preferred_api_base(target: TargetSite) -> str:
    for request in target.target_requests:
        parsed = urlparse(request.url)
        path = parsed.path or "/"
        if "/h5/" in path:
            prefix = path.split("/h5/", 1)[0] + "/h5"
            return f"{parsed.scheme}://{parsed.netloc}{prefix}"
    parsed = urlparse(target.url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
