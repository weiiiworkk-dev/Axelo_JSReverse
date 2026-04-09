"""Cap-5: Human behavior fragment library.

Stores and retrieves recorded real-human interaction fragments (mouse movements,
scrolls, clicks, pauses) for mixing with algorithmic paths to defeat ML-based
behavior detection systems (DataDome, PerimeterX, etc.).

Storage: ``{sessions_dir}/_behaviors/{fragment_type}/*.json``

Usage::

    bank = ReplayBank(sessions_dir)
    fragment = bank.sample("mouse_move", target_duration_ms=800)
    if fragment:
        # Use fragment.points instead of algorithmic path
        ...
    bank.add(BehaviorFragment(...))  # record a new human fragment
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class BehaviorFragment:
    """A single real-human interaction fragment."""
    fragment_type: str          # "scroll" | "click" | "mouse_move" | "pause" | "type"
    duration_ms: int
    points: list[dict]          # [{x, y, ts, pressure?, buttons?}] for pointer events
    metadata: dict = field(default_factory=dict)  # viewport size, UA, etc.
    recorded_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    source: str = "human"       # "human" | "synthetic"

    def adapt_to_viewport(self, target_width: int, target_height: int) -> "BehaviorFragment":
        """Scale coordinates to a different viewport size."""
        src_w = self.metadata.get("viewport_width", target_width)
        src_h = self.metadata.get("viewport_height", target_height)
        if src_w == target_width and src_h == target_height:
            return self
        sx = target_width / max(src_w, 1)
        sy = target_height / max(src_h, 1)
        scaled_points = [
            {**p, "x": p["x"] * sx, "y": p["y"] * sy}
            for p in self.points
        ]
        return BehaviorFragment(
            fragment_type=self.fragment_type,
            duration_ms=self.duration_ms,
            points=scaled_points,
            metadata={**self.metadata, "viewport_width": target_width, "viewport_height": target_height},
            recorded_at=self.recorded_at,
            source=self.source,
        )


class ReplayBank:
    """Persistent library of human behavior fragments.

    Fragments are stored as JSON files bucketed by fragment_type::

        {root}/_behaviors/mouse_move/frag_001.json
        {root}/_behaviors/scroll/frag_001.json
        ...

    The bank falls back gracefully to returning None when empty,
    so callers can degrade to algorithmic generation without errors.
    """

    def __init__(self, sessions_dir: Path | str) -> None:
        self._root = Path(sessions_dir) / "_behaviors"
        self._rng = random.Random()
        self._counter: int = 0

    def sample(
        self,
        fragment_type: str,
        target_duration_ms: int = 800,
        duration_tolerance: float = 0.5,
    ) -> BehaviorFragment | None:
        """Return a random fragment matching the requested type and approximate duration.

        Parameters
        ----------
        fragment_type:
            Type of fragment to retrieve (e.g. "mouse_move", "scroll").
        target_duration_ms:
            Target duration; fragments within ``target ± tolerance×target`` are preferred.
        duration_tolerance:
            Fraction of target_duration to accept (default 50%).

        Returns None if no matching fragments exist.
        """
        bucket_dir = self._root / fragment_type
        if not bucket_dir.exists():
            return None

        files = list(bucket_dir.glob("*.json"))
        if not files:
            return None

        # Filter by duration range
        min_ms = int(target_duration_ms * (1 - duration_tolerance))
        max_ms = int(target_duration_ms * (1 + duration_tolerance))
        candidates: list[Path] = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if min_ms <= data.get("duration_ms", 0) <= max_ms:
                    candidates.append(f)
            except Exception:
                continue

        if not candidates:
            candidates = files  # Fall back to any fragment

        chosen_path = self._rng.choice(candidates)
        try:
            data = json.loads(chosen_path.read_text(encoding="utf-8"))
            return BehaviorFragment(**{k: v for k, v in data.items() if k in BehaviorFragment.__dataclass_fields__})
        except Exception:
            return None

    def add(self, fragment: BehaviorFragment) -> Path:
        """Persist a new fragment to the bank and return its path."""
        bucket_dir = self._root / fragment.fragment_type
        bucket_dir.mkdir(parents=True, exist_ok=True)
        self._counter += 1
        ts = int(time.time() * 1000)
        path = bucket_dir / f"frag_{ts}_{self._counter}.json"
        path.write_text(json.dumps(asdict(fragment), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def count(self, fragment_type: str | None = None) -> int:
        """Return the number of stored fragments (optionally filtered by type)."""
        if fragment_type:
            bucket_dir = self._root / fragment_type
            return len(list(bucket_dir.glob("*.json"))) if bucket_dir.exists() else 0
        if not self._root.exists():
            return 0
        return sum(len(list(d.glob("*.json"))) for d in self._root.iterdir() if d.is_dir())

    def all_types(self) -> list[str]:
        """Return a list of all fragment types present in the bank."""
        if not self._root.exists():
            return []
        return [d.name for d in self._root.iterdir() if d.is_dir()]
