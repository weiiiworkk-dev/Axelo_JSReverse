from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from axelo.config import settings
from axelo.output import save_output


def main() -> int:
    script_path = Path(sys.argv[1])
    payload_path = Path(sys.argv[2])
    result_path = Path(sys.argv[3])

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    result = {
        "headers": {},
        "crawl_data": None,
        "output_path": None,
        "error": None,
    }

    instance = None
    try:
        spec = importlib.util.spec_from_file_location("axelo_gen", script_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load generated crawler module")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # required for Python 3.14 dataclasses: sys.modules.get(cls.__module__) must not be None
        spec.loader.exec_module(module)

        init_kwargs = payload.get("init_kwargs") or {}
        crawl_kwargs = payload.get("crawl_kwargs") or {}

        crawler_class = next(
            (
                value
                for value in vars(module).values()
                if isinstance(value, type) and hasattr(value, "crawl")
            ),
            None,
        )
        crawl_callable = None
        if crawler_class is not None:
            instance = crawler_class(**init_kwargs)
            crawl_callable = instance.crawl
        elif callable(getattr(module, "crawl", None)):
            crawl_callable = getattr(module, "crawl")
        else:
            raise RuntimeError("No class or function exposing crawl() was found")

        try:
            crawl_data = crawl_callable(**crawl_kwargs)
        except Exception as crawl_exc:
            result["error"] = f"crawl() execution failed: {crawl_exc}"
            crawl_data = None
        result["headers"] = getattr(instance, "_last_headers", {}) if instance is not None else {}
        result["crawl_data"] = _json_safe(crawl_data) if crawl_data is not None else None

        if crawl_data is not None:
            session_id = payload["session_id"]
            output_path = save_output(
                crawl_data,
                payload["output_format"],
                Path(payload.get("output_dir") or settings.session_dir(session_id)),
                run_id=session_id,
            )
            result["output_path"] = str(output_path) if output_path else None
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        if instance is not None and hasattr(instance, "close"):
            try:
                instance.close()
            except Exception:
                pass

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["error"] is None else 1


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        # Last-resort fallback: convert to string representation
        return repr(value)


if __name__ == "__main__":
    raise SystemExit(main())
