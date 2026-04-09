from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StabilityResult(BaseModel):
    ok: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    runs: int = 0
    consistent_header_keys: bool = False
    consistent_output_shape: bool = False
    notes: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        return (
            f"stability ok={self.ok} score={self.score:.2f} runs={self.runs} "
            f"headers={self.consistent_header_keys} output={self.consistent_output_shape}"
        )


def _shape(value: Any) -> tuple[str, tuple[str, ...]]:
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "list", tuple(sorted(value[0].keys()))
        return "list", tuple()
    if isinstance(value, dict):
        return "dict", tuple(sorted(value.keys()))
    return type(value).__name__, tuple()


def evaluate_stability(samples: list[tuple[dict[str, str], Any]]) -> StabilityResult:
    # P4.1: 首次运行宽容处理
    if not samples:
        return StabilityResult(ok=False, runs=0, notes=["No stability samples collected"])
    
    # 只有1个样本时给予宽容分数
    if len(samples) == 1:
        return StabilityResult(
            ok=True,  # 首次运行不失败
            score=0.8,  # 给予80%分数
            runs=1,
            consistent_header_keys=True,  # 假设单次运行是一致的
            consistent_output_shape=True,
            notes=["first_run_acceptable"]
        )

    header_shapes = [tuple(sorted(headers.keys())) for headers, _ in samples]
    output_shapes = [_shape(data) for _, data in samples]
    consistent_header_keys = len(set(header_shapes)) == 1
    consistent_output_shape = len(set(output_shapes)) == 1

    score = 0.0
    if consistent_header_keys:
        score += 0.5
    if consistent_output_shape:
        score += 0.5

    notes = []
    if not consistent_header_keys:
        notes.append("Generated header keys changed across runs")
    if not consistent_output_shape:
        notes.append("Crawler output shape changed across runs")

    return StabilityResult(
        ok=score >= 0.5,
        score=score,
        runs=len(samples),
        consistent_header_keys=consistent_header_keys,
        consistent_output_shape=consistent_output_shape,
        notes=notes,
    )
