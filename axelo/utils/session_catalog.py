from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from axelo.utils.domain import extract_site_domain


# Accept both legacy 3-letter codes (AAA) and new domain-derived codes (amazon_com)
SITE_CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SESSION_ID_PATTERN = re.compile(r"^(?P<site_code>[A-Za-z][A-Za-z0-9_]*)-(?P<ordinal>\d{6})$")


@dataclass(frozen=True)
class SessionAllocation:
    site_key: str
    site_code: str
    session_id: str
    site_dir: Path
    session_dir: Path


def canonical_site_key(url_or_host: str) -> str:
    site_key = extract_site_domain(url_or_host)
    if site_key:
        return site_key.lower()
    raw = (url_or_host or "").strip().lower()
    return raw or "unknown-site"


def parse_session_id(session_id: str) -> tuple[str, int] | None:
    match = SESSION_ID_PATTERN.fullmatch((session_id or "").strip())
    if not match:
        return None
    return match.group("site_code"), int(match.group("ordinal"))


def session_dir_for_id(sessions_root: Path, session_id: str) -> Path:
    parsed = parse_session_id(session_id)
    if parsed is None:
        return sessions_root / session_id
    site_code, _ = parsed
    return sessions_root / site_code / session_id


class SessionCatalog:
    def __init__(self, sessions_root: Path) -> None:
        self.sessions_root = Path(sessions_root)
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.sessions_root / "_site_registry.json"

    def allocate(self, *, url_or_host: str, requested_session_id: str = "") -> SessionAllocation:
        self.normalize_session_layout()
        registry, site_versions = self._scan_state()
        site_key = canonical_site_key(url_or_host)
        site_code = registry.get(site_key)
        if not site_code:
            site_code = self._next_site_code(set(registry.values()), site_key)
            registry[site_key] = site_code
        if requested_session_id:
            parsed = parse_session_id(requested_session_id)
            if parsed is None:
                raise ValueError("Session IDs must use the format AAA-000001.")
            requested_site_code, requested_ordinal = parsed
            if requested_site_code != site_code:
                raise ValueError(
                    f"Requested session code {requested_site_code} does not match site code {site_code} for {site_key}."
                )
            ordinal = requested_ordinal
        else:
            ordinal = site_versions.get(site_code, 0) + 1
        session_id = f"{site_code}-{ordinal:06d}"
        site_dir = self.sessions_root / site_code
        session_dir = site_dir / session_id
        self._write_site_manifest(site_dir=site_dir, site_key=site_key, site_code=site_code, latest_session_id=session_id)
        self._write_registry(registry)
        return SessionAllocation(
            site_key=site_key,
            site_code=site_code,
            session_id=session_id,
            site_dir=site_dir,
            session_dir=session_dir,
        )

    def list_sessions(self) -> list[dict[str, Any]]:
        self.normalize_session_layout()
        records: list[dict[str, Any]] = []
        for site_dir in sorted(self.sessions_root.iterdir(), key=lambda item: item.name):
            if not site_dir.is_dir() or not SITE_CODE_PATTERN.fullmatch(site_dir.name):
                continue
            site_manifest = self._read_json(site_dir / "site.json") or {}
            site_key = str(site_manifest.get("site_key") or "")
            for session_dir in sorted(site_dir.iterdir(), key=lambda item: item.name):
                if not session_dir.is_dir():
                    continue
                parsed = parse_session_id(session_dir.name)
                if parsed is None:
                    continue
                request = self._read_json(session_dir / "session_request.json") or {}
                records.append(
                    {
                        "site_code": site_dir.name,
                        "site_key": site_key or canonical_site_key(str(request.get("url") or "")),
                        "session_id": session_dir.name,
                        "path": str(session_dir),
                        "url": str(request.get("url") or ""),
                    }
                )
        records.sort(key=lambda item: (item["site_code"], item["session_id"]), reverse=True)
        return records

    def normalize_session_layout(self) -> None:
        registry, site_versions = self._scan_state(persist_registry=False)
        flat_run_dirs = sorted(
            [
                directory
                for directory in self.sessions_root.iterdir()
                if directory.is_dir() and directory.name.startswith("run_")
            ],
            key=lambda item: item.stat().st_mtime,
        )
        if not flat_run_dirs:
            return
        for flat_run_dir in flat_run_dirs:
            request = self._read_json(flat_run_dir / "session_request.json") or {}
            site_key = canonical_site_key(str(request.get("url") or flat_run_dir.name))
            site_code = registry.get(site_key)
            if not site_code:
                site_code = self._next_site_code(set(registry.values()), site_key)
                registry[site_key] = site_code
            ordinal = site_versions.get(site_code, 0) + 1
            site_versions[site_code] = ordinal
            session_id = f"{site_code}-{ordinal:06d}"
            site_dir = self.sessions_root / site_code
            session_dir = site_dir / session_id
            site_dir.mkdir(parents=True, exist_ok=True)
            self._write_site_manifest(site_dir=site_dir, site_key=site_key, site_code=site_code, latest_session_id=session_id)
            shutil.move(str(flat_run_dir), str(session_dir))
            self._rewrite_session_identity(session_dir, session_id=session_id, site_code=site_code, site_key=site_key)
        self._write_registry(registry)

    def _scan_state(self, *, persist_registry: bool = True) -> tuple[dict[str, str], dict[str, int]]:
        registry = self._load_registry()
        site_versions: dict[str, int] = {}
        for site_dir in self.sessions_root.iterdir():
            if not site_dir.is_dir() or not SITE_CODE_PATTERN.fullmatch(site_dir.name):
                continue
            site_manifest = self._read_json(site_dir / "site.json") or {}
            site_key = canonical_site_key(str(site_manifest.get("site_key") or site_manifest.get("url") or ""))
            if site_key != "unknown-site":
                registry.setdefault(site_key, site_dir.name)
            for session_dir in site_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                parsed = parse_session_id(session_dir.name)
                if parsed is None:
                    continue
                _, ordinal = parsed
                site_versions[site_dir.name] = max(site_versions.get(site_dir.name, 0), ordinal)
                if site_key == "unknown-site":
                    request = self._read_json(session_dir / "session_request.json") or {}
                    derived_key = canonical_site_key(str(request.get("url") or ""))
                    if derived_key != "unknown-site":
                        site_key = derived_key
                        registry.setdefault(site_key, site_dir.name)
            if site_key != "unknown-site":
                self._write_site_manifest(
                    site_dir=site_dir,
                    site_key=site_key,
                    site_code=site_dir.name,
                    latest_session_id=f"{site_dir.name}-{site_versions.get(site_dir.name, 0):06d}" if site_versions.get(site_dir.name) else "",
                )
        if persist_registry:
            self._write_registry(registry)
        return registry, site_versions

    def _rewrite_session_identity(self, session_dir: Path, *, session_id: str, site_code: str, site_key: str) -> None:
        request_path = session_dir / "session_request.json"
        request = self._read_json(request_path)
        if isinstance(request, dict):
            request["session_id"] = session_id
            metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
            metadata["site_code"] = site_code
            metadata["site_key"] = site_key
            request["metadata"] = metadata
            self._write_json(request_path, request)
        mission_path = session_dir / "artifacts" / "final" / "mission_report.json"
        mission_report = self._read_json(mission_path)
        if isinstance(mission_report, dict):
            mission_report["session_id"] = session_id
            mission_report["site_code"] = site_code
            mission_report["site_key"] = site_key
            self._write_json(mission_path, mission_report)
        index_path = session_dir / "artifacts" / "final" / "artifact_index.json"
        artifact_index = self._read_json(index_path)
        if isinstance(artifact_index, dict):
            artifact_index["session_id"] = session_id
            artifact_index["site_code"] = site_code
            artifact_index["site_key"] = site_key
            self._write_json(index_path, artifact_index)
        principal_path = session_dir / "logs" / "principal_state.json"
        principal_state = self._read_json(principal_path)
        if isinstance(principal_state, dict):
            mission = principal_state.get("mission") if isinstance(principal_state.get("mission"), dict) else None
            if mission is not None:
                mission["session_id"] = session_id
            self._write_json(principal_path, principal_state)

    def _write_site_manifest(self, *, site_dir: Path, site_key: str, site_code: str, latest_session_id: str) -> None:
        site_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = site_dir / "site.json"
        manifest = self._read_json(manifest_path) or {}
        payload = {
            "site_key": site_key,
            "site_code": site_code,
            "latest_session_id": latest_session_id or manifest.get("latest_session_id") or "",
            "path": str(site_dir),
        }
        self._write_json(manifest_path, payload)

    def _load_registry(self) -> dict[str, str]:
        payload = self._read_json(self.registry_path)
        if not isinstance(payload, dict):
            return {}
        registry: dict[str, str] = {}
        for key, value in payload.items():
            site_key = canonical_site_key(str(key))
            # Accept both legacy uppercase (AAA) and new lowercase (example_com) codes
            site_code = str(value or "")
            if not site_code:
                continue
            # Normalise legacy all-caps 3-letter codes to uppercase; keep new codes as-is
            if re.fullmatch(r"[A-Z]{3}", site_code.upper()) and len(site_code) == 3:
                site_code = site_code.upper()
            if site_key and SITE_CODE_PATTERN.fullmatch(site_code):
                registry[site_key] = site_code
        return registry

    def _write_registry(self, registry: dict[str, str]) -> None:
        payload = {key: value for key, value in sorted(registry.items())}
        self._write_json(self.registry_path, payload)

    def _next_site_code(self, existing_codes: set[str], site_key: str = "") -> str:
        """Derive a human-readable folder name from the site key (e.g. 'amazon_com')."""
        base = self._domain_to_code(site_key) if site_key else "site"
        if base not in existing_codes:
            return base
        # Append a numeric suffix if the base name is already taken
        for n in range(2, 1000):
            candidate = f"{base}_{n}"
            if candidate not in existing_codes:
                return candidate
        raise RuntimeError(f"Site code space exhausted for base '{base}'.")

    @staticmethod
    def _domain_to_code(site_key: str) -> str:
        """Convert a domain/site_key to a safe folder name, e.g. 'amazon.com' -> 'amazon_com'."""
        key = re.sub(r"^www\.", "", (site_key or "").lower())
        code = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        return code or "unknown_site"

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return None

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
