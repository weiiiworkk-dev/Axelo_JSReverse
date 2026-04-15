"""
gen_ts_contracts.py — Generates TypeScript interfaces from axelo/models/contracts.py Pydantic models.

Usage (from repo root):
  python scripts/gen_ts_contracts.py

Output:
  axelo/web/ui/src/generated/contracts.ts

Run this script whenever axelo/models/contracts.py changes to keep TypeScript
interfaces in sync. The generated file is gitignored; regenerate before builds.
"""
from __future__ import annotations

import sys
import types
import typing
from datetime import datetime
from pathlib import Path

# Allow importing axelo from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel

from axelo.models.contracts import (
    AuthSpec,
    ExecutionSpec,
    FieldEvidence,
    FieldSpec,
    MissionContract,
    OutputSpec,
    ReadinessAssessment,
    ScopeDefinition,
)

# Emit models in dependency order (referenced types before referencing types)
MODELS: list[type[BaseModel]] = [
    FieldSpec,
    FieldEvidence,
    ReadinessAssessment,
    ScopeDefinition,
    AuthSpec,
    ExecutionSpec,
    OutputSpec,
    MissionContract,
]


def _py_to_ts(annotation: object) -> str:
    """Recursively convert a Python type annotation to a TypeScript type string."""
    # Python 3.10+ union: X | Y  (types.UnionType)
    if hasattr(types, "UnionType") and isinstance(annotation, types.UnionType):
        args = typing.get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        suffix = " | null" if len(non_none) < len(args) else ""
        if len(non_none) == 1:
            return _py_to_ts(non_none[0]) + suffix
        return " | ".join(_py_to_ts(a) for a in non_none) + suffix

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # typing.Union / Optional[X]
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        suffix = " | null" if len(non_none) < len(args) else ""
        if len(non_none) == 1:
            return _py_to_ts(non_none[0]) + suffix
        return " | ".join(_py_to_ts(a) for a in non_none) + suffix

    # list[X]
    if origin is list:
        inner = _py_to_ts(args[0]) if args else "unknown"
        return f"{inner}[]"

    # dict[K, V]
    if origin is dict:
        k = _py_to_ts(args[0]) if args else "string"
        v = _py_to_ts(args[1]) if len(args) > 1 else "unknown"
        return f"Record<{k}, {v}>"

    # typing.Literal['a', 'b']
    if origin is typing.Literal:
        return " | ".join(f"'{a}'" if isinstance(a, str) else str(a) for a in args)

    # Primitive types
    if annotation is str:
        return "string"
    if annotation is int:
        return "number"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is datetime:
        return "string"  # ISO 8601 on the wire
    if annotation is typing.Any:
        return "unknown"

    # Nested Pydantic model — reference by name (must appear before this model in MODELS)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    # Fallback
    return "unknown"


def _model_to_interface(model: type[BaseModel]) -> str:
    """Emit a TypeScript interface for one Pydantic model."""
    lines: list[str] = [f"export interface {model.__name__} {{"]

    for field_name, field_info in model.model_fields.items():
        ts_type = _py_to_ts(field_info.annotation)

        # Field is optional in TS if it has any default (default or default_factory)
        has_default = (
            field_info.default is not None
            or field_info.default_factory is not None  # type: ignore[misc]
        )
        optional = "?" if has_default else ""

        lines.append(f"  {field_name}{optional}: {ts_type}")

    lines.append("}")
    return "\n".join(lines)


def generate() -> None:
    out_dir = Path(__file__).parent.parent / "axelo" / "web" / "ui" / "src" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "contracts.ts"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_names = ", ".join(m.__name__ for m in MODELS)

    header = (
        "// AUTO-GENERATED — do not edit manually\n"
        "// Source: axelo/models/contracts.py\n"
        "// Regenerate: python scripts/gen_ts_contracts.py\n"
        f"// Generated: {timestamp}\n"
        f"// Models: {model_names}\n"
    )

    body = "\n\n".join(_model_to_interface(m) for m in MODELS)
    out_file.write_text(header + "\n" + body + "\n", encoding="utf-8")

    print(f"[gen_ts_contracts] Written: {out_file}")
    print(f"[gen_ts_contracts] Models:  {model_names}")


if __name__ == "__main__":
    generate()
