from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from axelo.browser.cookie_lifetime_estimator import CookieLifetimeEstimator

log = structlog.get_logger()

_estimator = CookieLifetimeEstimator()

# Sanitise domain strings to safe filenames
_UNSAFE_CHARS = re.compile(r"[^a-zA-Z0-9._-]")


def _domain_to_filename(domain: str) -> str:
    safe = _UNSAFE_CHARS.sub("_", domain.strip().lower())
    return f"{safe}.jsonl"


@dataclass
class SessionKnowledge:
    """Knowledge record for a single crawl session."""

    domain: str
    recorded_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    # Configuration used
    fingerprint_config: dict[str, Any] = field(default_factory=dict)
    behavior_config: dict[str, Any] = field(default_factory=dict)
    transport_impersonate: str = "chrome124"

    # Outcome
    outcome: str = "unknown"          # "success" | "challenge_resolved" | "blocked" | "partial" | "unknown"
    blocked_signals: list[str] = field(default_factory=list)
    resolved_signals: list[str] = field(default_factory=list)
    request_success_rate: float = 0.0

    # Reusable state
    cookie_snapshot: dict[str, str] = field(default_factory=dict)
    cookie_recorded_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    storage_state_path: str | None = None


class SessionKnowledgeStore:
    """Per-domain knowledge base stored as JSONL files.

    Storage layout::

        {knowledge_root}/{domain}.jsonl

    Each line is a JSON-serialised ``SessionKnowledge``.  Records are
    appended incrementally; no full-file rewrites.

    The store is intentionally free of system-specific names — it records
    generic outcome signals so the knowledge generalises to unknown systems.
    """

    def __init__(self, sessions_dir: Path | str) -> None:
        self._root = Path(sessions_dir) / "_knowledge"

    def _path(self, domain: str) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        return self._root / _domain_to_filename(domain)

    @staticmethod
    def _etld_plus1(domain: str) -> str:
        """Extract eTLD+1 (e.g. 'www.example.com' → 'example.com')."""
        parts = domain.strip().lower().split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return domain

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, knowledge: SessionKnowledge) -> None:
        """Append a knowledge record for *domain* to the JSONL store."""
        path = self._path(knowledge.domain)
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(knowledge), ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("knowledge_record_failed", domain=knowledge.domain, error=str(exc))

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def _load_records(self, domain: str, max_age_days: int = 30) -> list[SessionKnowledge]:
        """Load records for *domain*, also aggregating records from eTLD+1 sibling files."""
        cutoff_ts = time.time() - max_age_days * 86400
        # Collect candidate paths: exact domain + www-prefixed + eTLD+1
        candidate_domains: list[str] = [domain]
        etld1 = self._etld_plus1(domain)
        if etld1 and etld1 != domain:
            candidate_domains.append(etld1)
            if not domain.startswith("www."):
                candidate_domains.append(f"www.{etld1}")

        records: list[SessionKnowledge] = []
        seen_lines: set[str] = set()
        for candidate in candidate_domains:
            path = self._path(candidate)
            if not path.exists():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line in seen_lines:
                        continue
                    seen_lines.add(line)
                    try:
                        data = json.loads(line)
                        rec = SessionKnowledge(**{k: v for k, v in data.items() if k in SessionKnowledge.__dataclass_fields__})
                        # Age filter
                        try:
                            rec_ts = datetime.fromisoformat(rec.recorded_at).timestamp()
                            if rec_ts < cutoff_ts:
                                continue
                        except Exception:
                            pass
                        records.append(rec)
                    except Exception:
                        continue
            except OSError:
                pass
        return records

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_best_config(self, domain: str) -> dict[str, Any] | None:
        """Return the fingerprint+behavior config with the highest success rate.

        Returns ``None`` if there is no relevant history.
        """
        records = self._load_records(domain)
        successful = [r for r in records if r.outcome in {"success", "challenge_resolved"}]
        if not successful:
            return None
        best = max(successful, key=lambda r: r.request_success_rate)
        return {
            **best.fingerprint_config,
            **best.behavior_config,
            "impersonate": best.transport_impersonate,
        }

    def get_valid_cookies(self, domain: str) -> dict[str, str] | None:
        """Return the most recent cookie snapshot if it is still within its estimated TTL.

        Returns ``None`` if no valid cookies are available.
        """
        records = self._load_records(domain)
        successful = [r for r in records if r.outcome in {"success", "challenge_resolved"} and r.cookie_snapshot]
        if not successful:
            return None

        # Sort by recorded_at descending and take the newest
        def _rec_ts(r: SessionKnowledge) -> float:
            try:
                return datetime.fromisoformat(r.cookie_recorded_at).timestamp()
            except Exception:
                return 0.0

        newest = max(successful, key=_rec_ts)
        recorded_ts = _rec_ts(newest)
        if recorded_ts == 0.0:
            return None

        # Estimate TTL as the minimum TTL across all cookies in the snapshot
        ttls = [_estimator.estimate(name) for name in newest.cookie_snapshot]
        min_ttl = min(ttls) if ttls else 120

        if time.time() - recorded_ts > min_ttl:
            return None  # Expired

        return dict(newest.cookie_snapshot)

    def get_blocked_patterns(self, domain: str) -> list[str]:
        """Return a deduplicated list of blocked signals seen for this domain."""
        records = self._load_records(domain)
        seen: set[str] = set()
        for r in records:
            seen.update(r.blocked_signals)
        return sorted(seen)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def prune_old_records(self, domain: str, max_age_days: int = 30) -> int:
        """Remove records older than *max_age_days* and return the count removed."""
        path = self._path(domain)
        if not path.exists():
            return 0
        all_lines = path.read_text(encoding="utf-8").splitlines()
        fresh_records = self._load_records(domain, max_age_days=max_age_days)
        pruned = len(all_lines) - len(fresh_records)
        if pruned > 0:
            fresh_lines = [json.dumps(asdict(r), ensure_ascii=False) for r in fresh_records]
            path.write_text("\n".join(fresh_lines) + ("\n" if fresh_lines else ""), encoding="utf-8")
        return pruned
