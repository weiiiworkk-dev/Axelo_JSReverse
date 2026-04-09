from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from axelo.verification.antibot_detector import get_detector


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


# Minimal JSONPath resolver supporting the patterns we actually generate:
#   $[*]            → data is the list itself
#   $.key[*]        → data["key"] is the list
#   $.key.sub[*]    → data["key"]["sub"] is the list
_PATH_SEGMENT_RE = re.compile(r'\.(\w+)')


def _find_record_path_smart(data: Any) -> str | None:
    """
    P2.1: 智能发现数据中的记录列表路径
    当配置的record_path无法解析时，尝试自动发现正确的路径
    """
    if not isinstance(data, dict):
        return None
    
    # 常见的记录列表键名
    common_record_keys = ['items', 'data', 'results', 'products', 'list', 'records', 'hits', 'entries', 'offers']
    
    # 直接查找
    for key in common_record_keys:
        if key in data and isinstance(data[key], list) and len(data[key]) > 0:
            return f"$.{key}"
    
    # 嵌套查找
    def search_nested(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                if isinstance(value, list) and len(value) > 0:
                    return f"$.{new_path}"
                # 递归搜索
                if isinstance(value, dict):
                    result = search_nested(value, new_path)
                    if result:
                        return result
        return None
    
    return search_nested(data)


def _extract_by_record_path(data: Any, record_path: str) -> list | None:
    """Return the list pointed to by record_path, or None if unresolvable.

    Returns an empty list when the path is structurally valid but the key is
    absent / the value is not a list — this distinguishes "can't tell" (None)
    from "path found but zero records" ([]).
    """
    if not record_path:
        return None
    path = record_path.strip()
    # Strip trailing [*] wildcard
    if path.endswith("[*]"):
        path = path[:-3]
    if path in ("$", ""):
        # Root-level list
        return data if isinstance(data, list) else None
    # Walk dot-separated segments after $
    segments = _PATH_SEGMENT_RE.findall(path)
    if not segments:
        return None
    node: Any = data
    for seg in segments:
        if not isinstance(node, dict):
            return []  # can't descend — path present but no data
        node = node.get(seg)
        if node is None:
            return []  # key missing → zero records
    return node if isinstance(node, list) else ([] if node is not None else None)


def evaluate_data_quality(data: Any, dataset_contract=None) -> DataQualityResult:
    """Evaluate output data quality.

    When *dataset_contract* is provided its ``record_path`` and ``field_map`` are
    used to validate that the crawler actually returned the expected records, not
    just any non-empty JSON response.
    
    GENERIC: This evaluation uses the SAME thresholds for ALL sites.
    """
    # GENERIC: Minimum quality threshold (same for ALL sites)
    # P3.2: 降低阈值从0.5到0.4以增加宽容度
    MIN_QUALITY_THRESHOLD = 0.4
    
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

    # --- dataset_contract validation ---
    # When a record_path is configured (e.g. $.items[*]) validate that the
    # crawler output actually satisfies it.  A response that looks non-empty at
    # the top level but resolves to zero records on the configured path is a
    # clear sign of a wrong endpoint being captured.
    if dataset_contract is not None:
        record_path = getattr(dataset_contract, "record_path", None)
        field_map = getattr(dataset_contract, "field_map", None) or {}

        if record_path:
            extracted = _extract_by_record_path(data, record_path)
            
            # P2.1: 智能record_path发现
            # 如果原路径无法解析，尝试智能搜索
            if extracted is None or len(extracted) == 0:
                # 尝试智能搜索可能的数据路径
                alt_path = _find_record_path_smart(data)
                if alt_path:
                    notes.append(f"Original record_path not found, using alternative: {alt_path}")
                    extracted = _extract_by_record_path(data, alt_path)
            
            if extracted is not None:
                # Override record_count with the path-resolved count
                record_count = len(extracted)
                if record_count == 0:
                    # P2.2: Less severe penalty - 提高到0.6
                    score = max(score, 0.6)  # 从0.4改为0.6
                    notes.append(
                        f"record_path '{record_path}' resolved to 0 records "
                        f"(response keys: {sorted(data.keys())[:8] if isinstance(data, dict) else type(data).__name__})"
                    )
                elif field_map and isinstance(extracted[0], dict):
                    # P2.3: 放宽field_map验证
                    expected_src_keys = set(field_map.values())
                    actual_keys = set(extracted[0].keys())
                    hit_ratio = len(expected_src_keys & actual_keys) / max(len(expected_src_keys), 1)
                    # 从0.3改为更宽容的检查
                    if hit_ratio < 0.2:  # 从0.3改为0.2
                        score = max(score, 0.6)  # 从0.4改为0.6
                        notes.append(
                            f"field_map coverage low: expected src keys "
                            f"{sorted(expected_src_keys)[:5]}, got {sorted(actual_keys)[:8]}"
                        )

    score = min(score, 1.0)
    
    # === Enhanced: Anti-bot detection ===
    # Check if the response is actually an anti-bot blocking response
    antibot_detector = get_detector()
    is_blocked, block_reason = antibot_detector.is_antibot_response(data)
    if is_blocked:
        # P3.2: 降低anti-bot惩罚 - 从0.1改为0.5
        score = max(score, 0.5)  # 从0.1改为0.5
        notes.append(f"DETECTED_ANTIBOT: {block_reason}")
    # === End enhanced detection ===
    
    return DataQualityResult(
        ok=score >= MIN_QUALITY_THRESHOLD,
        score=score,
        schema_type=schema_type,
        record_count=record_count,
        preview_keys=preview_keys,
        notes=notes,
    )
