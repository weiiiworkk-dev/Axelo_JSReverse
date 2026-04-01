from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DataQualityResult(BaseModel):
    ok: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    schema_type: str = "unknown"
    record_count: int = 0
    preview_keys: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        return (
            f"data_quality ok={self.ok} score={self.score:.2f} "
            f"schema={self.schema_type} records={self.record_count} keys={self.preview_keys}"
        )


def evaluate_data_quality(data: Any) -> DataQualityResult:
    notes: list[str] = []
    preview_keys: list[str] = []
    record_count = 0
    schema_type = type(data).__name__
    score = 0.0

    if isinstance(data, list):
        record_count = len(data)
        schema_type = "list"
        dict_rows = [row for row in data if isinstance(row, dict)]
        if dict_rows:
            preview_keys = sorted({key for row in dict_rows[:5] for key in row.keys()})[:10]
            score += 0.6
        if record_count > 0:
            score += 0.4
        else:
            notes.append("List output is empty")
    elif isinstance(data, dict):
        schema_type = "dict"
        preview_keys = sorted(list(data.keys()))[:10]
        if data:
            score += 0.5
        inner = data.get("data")
        if isinstance(inner, list):
            record_count = len(inner)
            if inner:
                score += 0.5
            else:
                notes.append("Dict contains empty data list")
        else:
            record_count = 1 if data else 0
            if data:
                score += 0.3
    elif data is None:
        notes.append("Crawler returned null output")
    else:
        notes.append(f"Unexpected output type: {type(data).__name__}")
        if data:
            record_count = 1
            score = 0.2

    score = min(score, 1.0)
    return DataQualityResult(
        ok=score >= 0.4,
        score=score,
        schema_type=schema_type,
        record_count=record_count,
        preview_keys=preview_keys,
        notes=notes,
    )
