from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactWriter:
    def __init__(self, session_path: Path) -> None:
        self.session_path = Path(session_path)

    def _resolve(self, relative: str) -> Path:
        return self.session_path / relative

    def write_json(self, relative: str, data: Any, indent: int = 2) -> Path:
        """Atomically write JSON file."""
        dest = self._resolve(relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.parent / (dest.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
        tmp.replace(dest)
        return dest

    def write_text(self, relative: str, content: str) -> Path:
        """Atomically write text file (for code files etc)."""
        dest = self._resolve(relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.parent / (dest.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(dest)
        return dest

    def append_jsonl(self, relative: str, record: dict[str, Any]) -> None:
        """Append one JSON line to a .jsonl file."""
        dest = self._resolve(relative)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
