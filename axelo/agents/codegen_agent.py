from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import structlog
from jinja2 import Environment, FileSystemLoader

from axelo.agents.base import BaseAgent
from axelo.ai.hypothesis import CodeGenOutput
from axelo.memory.retriever import MemoryRetriever
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.target import TargetSite

log = structlog.get_logger()

PROMPTS_DIR = Path(__file__).parent.parent / "ai" / "prompts"
BASE_BRIDGE_TEMPLATE = PROMPTS_DIR / "base_bridge_template.js"
BASE_CRAWLER_TEMPLATE = PROMPTS_DIR / "base_crawler_template.py"

CODEGEN_SYSTEM = """You are a crawler code generation agent.

Transform the reverse-engineering result into runnable crawler artifacts.
Always emit complete files, runnable imports, and deterministic helper methods.
Before sending the primary replay request, store the exact outgoing headers on `self._last_headers`.
When helpful for debugging, also keep the last replay URL on `self._last_request_url`.
"""


class CodeGenAgent(BaseAgent):
    role = "codegen"
    default_model = "claude-opus-4-6"

    def __init__(self, *args, retriever: MemoryRetriever, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._jinja = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

    async def generate(
        self,
        target: TargetSite,
        hypothesis: AIHypothesis,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        output_dir: Path,
    ) -> dict[str, Path]:
        algo_type = _infer_algo_type(hypothesis)
        templates = self._retriever.get_all_templates()
        template_code = ""
        for template_item in templates:
            if template_item.algorithm_type == algo_type and template_item.python_code:
                template_code = f"# reference template '{template_item.name}'\n{template_item.python_code}"
                break

        observed_context = _observed_request_context(target)
        grounding_rules = _render_grounding_rules(observed_context)
        if hypothesis.codegen_strategy == "python_reconstruct":
            system_prompt = (
                CODEGEN_SYSTEM
                + f"\n\nReference template:\n{template_code or '(none)'}"
                + f"\n\nHost grounding rules:\n{grounding_rules}"
            )
            source_snippets = _collect_snippets(hypothesis, static_results)
            hook_data = _collect_hook_data(dynamic)
            template = self._jinja.get_template("generate_python.j2")
            user_msg = template.render(
                hypothesis=hypothesis,
                source_snippets=source_snippets,
                hook_data=hook_data,
                target=target,
            )
            user_msg = (
                _render_observed_request_context(observed_context)
                + "\n\n"
                + user_msg
            )
            client = self._build_client()
            response = await client.analyze(
                system_prompt=system_prompt,
                user_message=user_msg,
                output_schema=CodeGenOutput,
                tool_name="codegen",
                max_tokens=8192,
            )
            output = response.data

            self._cost.add_ai_call(
                model=response.model,
                input_tok=response.input_tokens,
                output_tok=response.output_tokens,
                stage="codegen",
            )
        else:
            output = CodeGenOutput(
                crawler_code=_render_base_crawler_template(target, bridge_port=8721),
                dependencies=["httpx>=0.27.0"],
                bridge_server_code="",
                notes=_render_js_bridge_notes(target, hypothesis, bridge_port=8721),
            )

        artifacts: dict[str, Path] = {}
        output_dir.mkdir(parents=True, exist_ok=True)

        if output.crawler_code:
            output.crawler_code = _repair_generated_code_for_target(output.crawler_code, target)
            path = output_dir / "crawler.py"
            path.write_text(output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = path
        if hypothesis.codegen_strategy == "js_bridge":
            path = output_dir / "bridge_server.js"
            path.write_text(_render_base_bridge_template(target, bridge_port=8721), encoding="utf-8")
            artifacts["bridge_server"] = path
        elif output.bridge_server_code:
            path = output_dir / "bridge_server.js"
            path.write_text(output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = path
        if output.dependencies:
            path = output_dir / "requirements.txt"
            path.write_text("\n".join(output.dependencies), encoding="utf-8")
            artifacts["requirements"] = path

        manifest = {
            "strategy": hypothesis.codegen_strategy,
            "algorithm_description": hypothesis.algorithm_description,
            "signature_spec": hypothesis.signature_spec.model_dump(mode="json") if hypothesis.signature_spec else None,
            "notes": output.notes,
            "dependencies": output.dependencies,
        }
        manifest_path = output_dir / "crawler_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["manifest"] = manifest_path

        log.info("codegen_done", files=list(artifacts.keys()))
        return artifacts


def _infer_algo_type(hypothesis: AIHypothesis) -> str:
    desc = hypothesis.algorithm_description.lower()
    for keyword, algorithm_type in [
        ("hmac", "hmac"),
        ("rsa", "rsa"),
        ("aes", "aes"),
        ("md5", "md5"),
        ("canvas", "fingerprint"),
        ("fingerprint", "fingerprint"),
    ]:
        if keyword in desc:
            return algorithm_type
    return "custom"


def _collect_snippets(hypothesis: AIHypothesis, static_results: dict[str, StaticAnalysis]) -> str:
    snippets: list[str] = []
    for static in static_results.values():
        for candidate in static.token_candidates:
            if candidate.func_id in hypothesis.generator_func_ids and candidate.source_snippet:
                snippets.append(f"// {candidate.func_id}\n{candidate.source_snippet[:600]}")
    return "\n\n".join(snippets[:4]) or "(no source snippets found)"


def _collect_hook_data(dynamic: DynamicAnalysis | None) -> str:
    if not dynamic or not dynamic.hook_intercepts:
        return "(no dynamic hook data)"
    return json.dumps(
        [item.model_dump(mode="json") for item in dynamic.hook_intercepts[:5]],
        ensure_ascii=False,
        indent=2,
    )


def _observed_request_context(target: TargetSite) -> dict[str, object]:
    page_origin = _page_origin(target.url)
    preferred_api_base = _preferred_api_base(target)
    observed_urls = [request.url for request in target.target_requests[:5]]
    site_suffix = _site_suffix(target.url)
    cookie_domain = f".{site_suffix}" if site_suffix else ""
    return {
        "page_origin": page_origin,
        "preferred_api_base": preferred_api_base,
        "observed_urls": observed_urls,
        "site_suffix": site_suffix,
        "cookie_domain": cookie_domain,
    }


def _render_grounding_rules(context: dict[str, object]) -> str:
    lines = [
        "- Never invent domains or API hosts that were not observed in captured traffic.",
        f"- Prefer this page origin: {context.get('page_origin') or '(unknown)'}",
        f"- Prefer this API base when generating crawler constants: {context.get('preferred_api_base') or '(none observed)'}",
        f"- If you need a cookie domain, preserve the exact site suffix: {context.get('cookie_domain') or '(unknown)'}",
    ]
    return "\n".join(lines)


def _render_observed_request_context(context: dict[str, object]) -> str:
    observed_urls = context.get("observed_urls") or []
    observed_block = "\n".join(f"- {url}" for url in observed_urls) if observed_urls else "- (none)"
    return (
        "## Grounded request context\n"
        f"- Page origin: {context.get('page_origin') or '(unknown)'}\n"
        f"- Preferred API base: {context.get('preferred_api_base') or '(none observed)'}\n"
        f"- Cookie domain: {context.get('cookie_domain') or '(unknown)'}\n"
        "- Observed request URLs:\n"
        f"{observed_block}"
    )


def _preferred_api_base(target: TargetSite) -> str:
    for request in target.target_requests:
        parsed = urlsplit(request.url)
        path = parsed.path or "/"
        if "/h5/" in path:
            prefix = path.split("/h5/", 1)[0] + "/h5"
            return f"{parsed.scheme}://{parsed.netloc}{prefix}"
    for request in target.target_requests:
        parsed = urlsplit(request.url)
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _page_origin(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _site_suffix(url: str) -> str:
    host = urlsplit(url).hostname or ""
    if host.startswith("www."):
        return host[4:]
    return host


def _repair_generated_code_for_target(code: str, target: TargetSite) -> str:
    if not code:
        return code

    page_origin = _page_origin(target.url)
    preferred_api_base = _preferred_api_base(target)
    site_suffix = _site_suffix(target.url)
    shorter_suffix = ".".join(site_suffix.split(".")[:-1]) if site_suffix.count(".") >= 2 else ""

    if preferred_api_base:
        code = re.sub(
            r'https://(?:h5api\.m|acs-m)\.[A-Za-z0-9.-]+/h5',
            preferred_api_base,
            code,
        )
    if preferred_api_base and "MTOP_BASE_URL" in code:
        code = re.sub(
            r'(MTOP_BASE_URL\s*=\s*[\'"])[^\'"]+([\'"])',
            lambda match: f"{match.group(1)}{preferred_api_base}{match.group(2)}",
            code,
        )
    if page_origin and "SEED_URL" in code:
        code = re.sub(
            r'(SEED_URL\s*=\s*[\'"])[^\'"]+([\'"])',
            lambda match: f"{match.group(1)}{page_origin}/{match.group(2)}",
            code,
        )
    if page_origin:
        host = urlsplit(page_origin).netloc
        code = re.sub(
            r'https://www\.[A-Za-z0-9.-]+/',
            f"https://{host}/",
            code,
        )
    if site_suffix and shorter_suffix:
        code = re.sub(
            rf'([\'"])\.{re.escape(shorter_suffix)}([\'"])',
            lambda match: f"{match.group(1)}.{site_suffix}{match.group(2)}",
            code,
        )
    return code


def _render_base_bridge_template(target: TargetSite, bridge_port: int) -> str:
    raw = BASE_BRIDGE_TEMPLATE.read_text(encoding="utf-8")
    storage_state_path = (
        str(Path(target.session_state.storage_state_path).resolve())
        if target.session_state.storage_state_path
        else ""
    )
    replacements = {
        "__AXELO_BRIDGE_PORT__": str(bridge_port),
        "__AXELO_START_URL__": json.dumps(target.url or "", ensure_ascii=False),
        "__AXELO_STORAGE_STATE_PATH__": json.dumps(storage_state_path, ensure_ascii=False),
        "__AXELO_DEFAULT_APP_KEY__": json.dumps(_default_app_key(target), ensure_ascii=False),
    }
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    return raw


def _render_base_crawler_template(target: TargetSite, bridge_port: int) -> str:
    raw = BASE_CRAWLER_TEMPLATE.read_text(encoding="utf-8")
    storage_state_path = (
        str(Path(target.session_state.storage_state_path).resolve())
        if target.session_state.storage_state_path
        else ""
    )
    replacements = {
        "__AXELO_CRAWLER_CLASS__": _crawler_class_name(target.url),
        "__AXELO_BRIDGE_PORT__": str(bridge_port),
        "__AXELO_PAGE_ORIGIN__": json.dumps(_page_origin(target.url), ensure_ascii=False),
        "__AXELO_START_URL__": json.dumps(target.url or "", ensure_ascii=False),
        "__AXELO_KNOWN_ENDPOINT__": json.dumps(target.known_endpoint or "", ensure_ascii=False),
        "__AXELO_PREFERRED_API_BASE__": json.dumps(_preferred_api_base(target), ensure_ascii=False),
        "__AXELO_BRIDGE_LOCALE__": json.dumps(target.browser_profile.locale or "en-US", ensure_ascii=False),
        "__AXELO_BRIDGE_TIMEZONE__": json.dumps(target.browser_profile.timezone or "UTC", ensure_ascii=False),
        "__AXELO_STORAGE_STATE_PATH__": json.dumps(storage_state_path, ensure_ascii=False),
        "__AXELO_DEFAULT_HEADERS__": json.dumps(_safe_default_headers(target), ensure_ascii=False, indent=4),
        "__AXELO_OBSERVED_TARGETS__": json.dumps(_observed_targets_payload(target), ensure_ascii=False, indent=4),
    }
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    return raw


def _default_app_key(target: TargetSite) -> str:
    for request in target.target_requests:
        parsed = urlsplit(request.url)
        query = parse_qs(parsed.query)
        for key in ("appKey", "appkey", "app_key"):
            values = query.get(key)
            if values and values[0]:
                return values[0]
    return ""


def _crawler_class_name(url: str) -> str:
    host = urlsplit(url).hostname or "generated"
    parts = []
    for chunk in host.split("."):
        cleaned = re.sub(r"[^A-Za-z0-9]+", " ", chunk).strip()
        if not cleaned or cleaned.lower() in {"www", "com", "net", "org"}:
            continue
        parts.append("".join(piece.capitalize() for piece in cleaned.split()))
    return "".join(parts or ["Generated", "Bridge"]) + "Crawler"


def _safe_default_headers(target: TargetSite) -> dict[str, str]:
    headers: dict[str, str] = {}
    for request in target.target_requests:
        headers.update(_filter_default_headers(request.request_headers))

    observed_user_agent = headers.get("User-Agent") or headers.get("user-agent") or ""
    user_agent = _canonical_user_agent(target.browser_profile.user_agent or observed_user_agent) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    locale = target.browser_profile.locale or "en-US"
    page_origin = _page_origin(target.url)

    normalized = {
        "User-Agent": user_agent,
        "Accept": headers.get("Accept") or "application/json, text/plain, */*",
        "Accept-Language": headers.get("Accept-Language") or locale,
        "Referer": headers.get("Referer") or (f"{target.url}" if target.url else ""),
        "Origin": headers.get("Origin") or page_origin,
    }
    if headers.get("Content-Type"):
        normalized["Content-Type"] = headers["Content-Type"]
    if headers.get("X-Requested-With"):
        normalized["X-Requested-With"] = headers["X-Requested-With"]
    for key, value in headers.items():
        lowered = key.lower()
        if lowered.startswith("x-csrf") and value:
            normalized[key] = value
    return {key: value for key, value in normalized.items() if value}


def _filter_default_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed = {
        "accept",
        "accept-language",
        "content-type",
        "origin",
        "referer",
        "user-agent",
        "x-requested-with",
    }
    filtered: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if not value:
            continue
        if lowered in {"cookie", "content-length", "host", "connection"}:
            continue
        if lowered.startswith("sec-"):
            continue
        if lowered in allowed or lowered.startswith("x-csrf"):
            filtered[key] = value
    return filtered


def _filter_observed_target_headers(headers: dict[str, str]) -> dict[str, str]:
    filtered: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if not value:
            continue
        if lowered in {"content-type", "accept", "x-requested-with"} or lowered.startswith("x-csrf"):
            filtered[key] = value
    return filtered


def _canonical_user_agent(user_agent: str) -> str:
    if not user_agent:
        return ""
    return user_agent.replace("HeadlessChrome/", "Chrome/")


def _observed_targets_payload(target: TargetSite) -> list[dict[str, object]]:
    observed: list[dict[str, object]] = []
    source_requests = target.target_requests or target.captured_requests
    for index, request in enumerate(source_requests[:5]):
        body_text = _request_body_to_text(request.request_body)
        observed.append(
            {
                "name": _observed_target_name(request.url, index),
                "url": request.url,
                "method": request.method or "GET",
                "headers": _filter_observed_target_headers(request.request_headers),
                "body": body_text,
            }
        )
    return observed


def _observed_target_name(url: str, index: int) -> str:
    parsed = urlsplit(url)
    tail = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
    if tail:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", tail).strip("_")
        if cleaned:
            return cleaned.lower()
    return f"target_{index + 1}"


def _request_body_to_text(body: bytes | None) -> str:
    if not body:
        return ""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def _render_js_bridge_notes(target: TargetSite, hypothesis: AIHypothesis, bridge_port: int) -> str:
    return (
        "## Implementation Notes\n\n"
        "### Architecture\n"
        "- `bridge_server.js` is rendered from `axelo/ai/prompts/base_bridge_template.js`.\n"
        "- `crawler.py` is rendered from `axelo/ai/prompts/base_crawler_template.py`.\n"
        "- Both files use the fixed Playwright-backed bridge protocol instead of model-generated custom implementations.\n\n"
        "### Runtime Requirements\n"
        "- Python dependency: `httpx>=0.27.0`\n"
        "- Node dependency: `playwright`\n"
        "- Browser install step: `npx playwright install chromium`\n\n"
        "### Safety / Scope\n"
        "- This implementation depends on a real browser context.\n"
        "- It does not include webdriver spoofing, stealth plugins, or CDP-hiding logic.\n"
        "- Challenge and crash states are surfaced back to Python rather than bypassed.\n\n"
        "### Current Session Defaults\n"
        f"- Start URL: `{target.url}`\n"
        f"- Storage state: `{target.session_state.storage_state_path or '(none)'}`\n"
        f"- Bridge port: `{bridge_port}`\n"
        f"- Strategy: `{hypothesis.codegen_strategy}`"
    )
