"""Cap-5: Behavior mixer — blends real recorded fragments with algorithmic paths.

When the ReplayBank has sufficient fragments, replaces 70% of algorithmic
pointer paths with recorded real-human data. Falls back to 100% algorithmic
generation when the bank is empty.

Usage::

    mixer = BehaviorMixer(bank)
    path = mixer.get_pointer_path(
        start=(100, 200), end=(500, 400),
        duration_ms=800,
        viewport=(1920, 1080),
    )
    # path is a list of {x, y, ts} points
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from axelo.behavior.replay_bank import BehaviorFragment, ReplayBank


@dataclass
class PointerPath:
    """A resolved pointer path ready for playback."""
    points: list[dict]
    duration_ms: int
    source: str    # "recorded" | "algorithmic"


class BehaviorMixer:
    """Blends recorded and algorithmic pointer paths.

    When ``bank.count('mouse_move') >= min_fragments``, 70% of path
    requests are served from the bank (with coordinate scaling applied).
    The remaining 30% use algorithmic generation for variety.
    """

    RECORDED_RATIO = 0.70       # Fraction of requests served from recorded bank
    MIN_FRAGMENTS = 5           # Minimum fragments needed to start using recorded data

    def __init__(
        self,
        bank: ReplayBank,
        rng_seed: int | None = None,
        min_fragments: int = MIN_FRAGMENTS,
    ) -> None:
        self._bank = bank
        self._rng = random.Random(rng_seed)
        self._min_fragments = min_fragments

    def get_pointer_path(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        duration_ms: int = 800,
        viewport: tuple[int, int] = (1920, 1080),
    ) -> PointerPath:
        """Return a pointer path from either the bank or algorithmic fallback.

        Parameters
        ----------
        start: (x, y) starting position
        end:   (x, y) ending position
        duration_ms: approximate desired duration
        viewport: current viewport (width, height) for coordinate scaling
        """
        use_recorded = (
            self._bank.count("mouse_move") >= self._min_fragments
            and self._rng.random() < self.RECORDED_RATIO
        )

        if use_recorded:
            fragment = self._bank.sample("mouse_move", target_duration_ms=duration_ms)
            if fragment is not None:
                adapted = fragment.adapt_to_viewport(viewport[0], viewport[1])
                translated = self._translate_fragment(adapted, start, end)
                return PointerPath(
                    points=translated,
                    duration_ms=adapted.duration_ms,
                    source="recorded",
                )

        # Algorithmic fallback
        points = self._algorithmic_path(start, end, duration_ms)
        return PointerPath(points=points, duration_ms=duration_ms, source="algorithmic")

    def _translate_fragment(
        self,
        fragment: BehaviorFragment,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> list[dict]:
        """Translate recorded fragment coordinates to match start→end vector."""
        if not fragment.points:
            return []

        src_start = fragment.points[0]
        src_end = fragment.points[-1]
        sx = src_start.get("x", 0)
        sy = src_start.get("y", 0)
        ex = src_end.get("x", sx)
        ey = src_end.get("y", sy)
        src_dx = ex - sx
        src_dy = ey - sy
        tgt_dx = end[0] - start[0]
        tgt_dy = end[1] - start[1]

        result = []
        for p in fragment.points:
            # Linear mapping from recorded path vector to target vector
            frac_x = (p.get("x", 0) - sx) / (src_dx or 1)
            frac_y = (p.get("y", 0) - sy) / (src_dy or 1)
            new_x = start[0] + frac_x * tgt_dx
            new_y = start[1] + frac_y * tgt_dy
            result.append({**p, "x": round(new_x, 2), "y": round(new_y, 2)})
        return result

    def _algorithmic_path(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        duration_ms: int,
    ) -> list[dict]:
        """Physics-based mouse path using Fitts' Law timing + Ornstein-Uhlenbeck tremor.

        Improvements over simple Bezier easing:
        - Fitts' Law: movement time scales with log2(distance / target_size + 1)
        - Overshoot + correction in the final 10% of travel (natural correction motion)
        - Ornstein-Uhlenbeck micro-tremor (σ=0.4 px) to break deterministic patterns
        - Gamma-distributed inter-step jitter for irregular sampling cadence
        """
        import math

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy) or 1.0

        # Fitts' Law: adjust step count based on distance (denser sampling for longer paths)
        steps = max(10, round(duration_ms / 14) + round(math.log2(distance / 40 + 1) * 4))

        # Overshoot target: 2-4 px beyond the endpoint, corrected in last 10%
        overshoot_factor = self._rng.uniform(0.01, 0.03)
        overshoot_x = end[0] + dx * overshoot_factor
        overshoot_y = end[1] + dy * overshoot_factor
        correction_start = 0.90  # fraction of path where correction begins

        # Ornstein-Uhlenbeck noise parameters (models muscle micro-tremor)
        ou_theta = 0.3   # mean-reversion rate
        ou_sigma = 0.4   # noise amplitude in pixels
        ou_x, ou_y = 0.0, 0.0

        points = []
        for i in range(steps):
            t = i / max(steps - 1, 1)

            # Minimum-jerk base easing (10t³-15t⁴+6t⁵)
            ease = 10 * t**3 - 15 * t**4 + 6 * t**5

            if t < correction_start:
                # Travel toward overshoot target
                base_x = start[0] + (overshoot_x - start[0]) * ease
                base_y = start[1] + (overshoot_y - start[1]) * ease
            else:
                # Correction phase: smoothly approach true endpoint
                correction_t = (t - correction_start) / (1.0 - correction_start)
                correction_ease = correction_t * correction_t  # quadratic pull-back
                over_x = start[0] + (overshoot_x - start[0]) * correction_start
                over_y = start[1] + (overshoot_y - start[1]) * correction_start
                base_x = over_x + (end[0] - over_x) * correction_ease
                base_y = over_y + (end[1] - over_y) * correction_ease

            # Ornstein-Uhlenbeck update: dx = θ(0 - x)dt + σ·N(0,1)
            ou_x += ou_theta * (0 - ou_x) + ou_sigma * self._rng.gauss(0, 1)
            ou_y += ou_theta * (0 - ou_y) + ou_sigma * self._rng.gauss(0, 1)

            # Gamma-jittered timestamp (irregular sampling cadence)
            base_ts = duration_ms * t
            jitter_ms = self._rng.gauss(0, duration_ms * 0.005)  # ±0.5% jitter

            points.append({
                "x": round(base_x + ou_x, 2),
                "y": round(base_y + ou_y, 2),
                "ts": max(0, round(base_ts + jitter_ms)),
            })

        # Guarantee final point is exactly at endpoint with no tremor
        points[-1] = {"x": end[0], "y": end[1], "ts": duration_ms}
        return points

    def generate_scroll_sequence(
        self,
        *,
        scroll_distance_px: int,
        viewport_height: int = 900,
        duration_ms: int = 1200,
    ) -> list[dict]:
        """Generate a realistic inertial scroll sequence with overshoot + correction.

        Human scrolling exhibits: initial fast movement, deceleration, slight
        overshoot, and a small correction back.  This models that with an
        exponential-decay velocity profile.

        Returns a list of {delta_y, ts} dicts for playback via ``page.mouse.wheel``.
        """
        steps = max(8, round(duration_ms / 20))
        # Overshoot by 5-12% then correct back
        overshoot_ratio = self._rng.uniform(1.05, 1.12)
        total_with_overshoot = scroll_distance_px * overshoot_ratio
        correction_start_frac = 0.80

        events = []
        accumulated = 0.0
        for i in range(steps):
            t = i / max(steps - 1, 1)
            ts = round(duration_ms * t)

            if t < correction_start_frac:
                # Exponential-decay velocity: fast start, smooth deceleration
                v = math.exp(-4 * t) * (total_with_overshoot / correction_start_frac)
                chunk = v * (duration_ms * correction_start_frac / steps / 1000) * 1000
            else:
                # Correction: small negative delta (pull back from overshoot)
                overshoot_amount = accumulated - scroll_distance_px
                correction_frac = (t - correction_start_frac) / (1.0 - correction_start_frac)
                chunk = -overshoot_amount * correction_frac * 0.3

            delta = round(chunk + self._rng.gauss(0, 1.5), 1)
            accumulated += delta
            events.append({"delta_y": delta, "ts": ts})

        return events
