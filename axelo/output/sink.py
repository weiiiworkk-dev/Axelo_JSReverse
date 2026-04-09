from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def save_output(data: Any, output_format: str, output_dir: Path, run_id: str = "") -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{run_id}_" if run_id else ""

    if output_format == "json_file":
        out = output_dir / f"{prefix}results.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    if output_format == "csv":
        out = output_dir / f"{prefix}results.csv"
        rows: list[dict[str, Any]]
        if isinstance(data, list):
            rows = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, list):
                rows = [r for r in inner if isinstance(r, dict)]
            else:
                rows = [data]
        else:
            rows = []

        if rows:
            headers = sorted({k for row in rows for k in row.keys()})
            with out.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
            return out
        return None

    # print/custom modes are handled by generated code; no framework-side file output.
    return None

