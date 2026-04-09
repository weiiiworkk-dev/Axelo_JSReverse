from __future__ import annotations

import json
import re
from pprint import pformat
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import structlog

from axelo.analysis.request_contracts import build_dataset_contract, derive_capability_profile
from axelo.ai.hypothesis import CodeGenOutput
from axelo.browser.simulation import SIMULATION_INIT_SCRIPT_TEMPLATE, build_simulation_payload
from axelo.config import settings
from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.contracts import AdapterPackage, RequestContract, VerificationProfile
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


class GroundingService:
    def observed_request_context(self, target: TargetSite) -> dict[str, object]:
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

    def render_grounding_rules(self, context: dict[str, object]) -> str:
        lines = [
            "- Never invent domains or API hosts that were not observed in captured traffic.",
            f"- Prefer this page origin: {context.get('page_origin') or '(unknown)'}",
            f"- Prefer this API base when generating crawler constants: {context.get('preferred_api_base') or '(none observed)'}",
            f"- If you need a cookie domain, preserve the exact site suffix: {context.get('cookie_domain') or '(unknown)'}",
        ]
        return "\n".join(lines)

    def render_observed_request_context(self, context: dict[str, object]) -> str:
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

    def preferred_api_base(self, target: TargetSite) -> str:
        return _preferred_api_base(target)

    def repair_generated_code_for_target(self, code: str, target: TargetSite) -> str:
        return _repair_generated_code_for_target(code, target)


class TemplateCodegenService:
    _BUILTIN_TEMPLATE_NAMES = {"contract_replay", "observed-replay-template"}

    def select_template(self, hypothesis: AIHypothesis, templates) -> tuple[object | None, str]:
        algo_type = _infer_algo_type(hypothesis)
        template_code = ""
        selected_template = None
        for template_item in templates:
            if hypothesis.template_name and template_item.name == hypothesis.template_name:
                selected_template = template_item
                if template_item.python_code:
                    template_code = f"# reference template '{template_item.name}'\n{template_item.python_code}"
                break
            if template_item.algorithm_type == algo_type and template_item.python_code:
                if selected_template is None:
                    selected_template = template_item
                template_code = f"# reference template '{template_item.name}'\n{template_item.python_code}"
        return selected_template, template_code

    def supports_builtin(self, hypothesis: AIHypothesis) -> bool:
        return hypothesis.template_name in self._BUILTIN_TEMPLATE_NAMES

    def is_ready(self, hypothesis: AIHypothesis, template_item) -> bool:
        return _template_is_ready(hypothesis, template_item)

    def render_builtin(
        self,
        target: TargetSite,
        hypothesis: AIHypothesis,
        dynamic: DynamicAnalysis | None = None,
    ) -> CodeGenOutput:
        return _render_contract_replay_codegen(target, hypothesis, dynamic=dynamic)

    def render(
        self,
        template_item,
        target: TargetSite,
        hypothesis: AIHypothesis,
        dynamic: DynamicAnalysis | None = None,
    ) -> CodeGenOutput:
        return _render_template_codegen(template_item, target, hypothesis, dynamic=dynamic)


class AICodegenService:
    def __init__(self, *, agent, jinja, grounding: GroundingService) -> None:
        self._agent = agent
        self._jinja = jinja
        self._grounding = grounding

    async def generate(
        self,
        *,
        target: TargetSite,
        hypothesis: AIHypothesis,
        static_results: dict[str, StaticAnalysis],
        dynamic: DynamicAnalysis | None,
        template_code: str,
    ) -> CodeGenOutput:
        algo_type = _infer_algo_type(hypothesis)
        observed_context = self._grounding.observed_request_context(target)
        grounding_rules = self._grounding.render_grounding_rules(observed_context)

        if hypothesis.codegen_strategy == "python_reconstruct":
            # Cost-B: DeepSeek model routing based on algorithm complexity
            _STANDARD_ALGOS = {"hmac", "md5", "sha256", "sha1", "aes", "rsa", "base64"}
            if algo_type in _STANDARD_ALGOS and template_code:
                self._agent.default_model = "deepseek-chat"
                max_tokens_codegen = 4096
            elif algo_type == "custom" and not template_code:
                self._agent.default_model = "deepseek-reasoner"
                max_tokens_codegen = 4096
            else:
                self._agent.default_model = "deepseek-chat"
                max_tokens_codegen = 3072  # Cost-E: reduced from 4096
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
            user_msg = self._grounding.render_observed_request_context(observed_context) + "\n\n" + user_msg
            client = self._agent._build_client()
            response = await client.analyze(
                system_prompt=system_prompt,
                user_message=user_msg,
                output_schema=CodeGenOutput,
                tool_name="codegen",
                max_tokens=max_tokens_codegen,
            )
            output = response.data
            self._agent._cost.add_ai_call(
                model=response.model,
                input_tok=response.input_tokens,
                output_tok=response.output_tokens,
                stage="codegen",
            )
            if not output.crawler_code and response.output_tokens >= max_tokens_codegen:
                log.warning(
                    "codegen_truncated",
                    model=response.model,
                    output_tokens=response.output_tokens,
                    max_tokens=max_tokens_codegen,
                )
            return output

        return CodeGenOutput(
            crawler_code=_render_base_crawler_template(
                target,
                hypothesis=hypothesis,
                dynamic=dynamic,
                bridge_port=8721,
            ),
            dependencies=["curl_cffi>=0.7.0", "httpx>=0.27.0"],
            bridge_server_code="",
            notes=_render_js_bridge_notes(target, hypothesis, bridge_port=8721),
        )


class ArtifactWriter:
    def __init__(self, *, grounding: GroundingService) -> None:
        self._grounding = grounding

    def write(
        self,
        *,
        output: CodeGenOutput,
        hypothesis: AIHypothesis,
        target: TargetSite,
        dynamic: DynamicAnalysis | None,
        output_dir: Path,
    ) -> dict[str, Path]:
        artifacts: dict[str, Path] = {}
        output_dir.mkdir(parents=True, exist_ok=True)
        request_contract = target.selected_contract or RequestContract()
        dataset_contract = build_dataset_contract(target, request_contract)
        capability_profile = derive_capability_profile(
            target,
            contract=request_contract,
            codegen_strategy=hypothesis.codegen_strategy,
        )

        run_id = target.session_id
        prefix = f"{run_id}_" if run_id else ""

        if output.crawler_code:
            output.crawler_code = self._grounding.repair_generated_code_for_target(output.crawler_code, target)
            path = output_dir / f"{prefix}crawler.py"
            path.write_text(output.crawler_code, encoding="utf-8")
            artifacts["crawler_script"] = path
        if hypothesis.codegen_strategy == "js_bridge":
            path = output_dir / f"{prefix}bridge_server.js"
            path.write_text(
                _render_base_bridge_template(
                    target,
                    hypothesis=hypothesis,
                    dynamic=dynamic,
                    bridge_port=8721,
                ),
                encoding="utf-8",
            )
            artifacts["bridge_server"] = path
        elif output.bridge_server_code:
            path = output_dir / f"{prefix}bridge_server.js"
            path.write_text(output.bridge_server_code, encoding="utf-8")
            artifacts["bridge_server"] = path
        if output.dependencies:
            path = output_dir / "requirements.txt"
            path.write_text("\n".join(output.dependencies), encoding="utf-8")
            artifacts["requirements"] = path

        manifest = {
            "site_key": urlsplit(target.url).netloc,
            "intent": target.intent.model_dump(mode="json"),
            "family_id": hypothesis.family_id or (hypothesis.signature_spec.family_id if hypothesis.signature_spec else "unknown"),
            "strategy": hypothesis.codegen_strategy,
            "algorithm_description": hypothesis.algorithm_description,
            "request_contract": request_contract.model_dump(mode="json"),
            "signature_spec": hypothesis.signature_spec.model_dump(mode="json") if hypothesis.signature_spec else None,
            "capability_profile": capability_profile.model_dump(mode="json"),
            "dataset_contract": dataset_contract.model_dump(mode="json"),
            "notes": output.notes,
            "dependencies": output.dependencies,
        }
        manifest_path = output_dir / f"{prefix}manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["manifest"] = manifest_path
        package = _build_adapter_package(
            target=target,
            hypothesis=hypothesis,
            request_contract=request_contract,
            dataset_contract=dataset_contract,
            capability_profile=capability_profile,
            crawler_artifact=str(artifacts.get("crawler_script") or ""),
            bridge_artifact=str(artifacts.get("bridge_server") or ""),
            manifest=manifest,
            manifest_ref=str(manifest_path),
        )
        adapter_package_path = output_dir / "adapter_package.json"
        adapter_package_path.write_text(json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["adapter_package"] = adapter_package_path
        log.info("codegen_done", files=list(artifacts.keys()))
        return artifacts


def _infer_algo_type(hypothesis: AIHypothesis) -> str:
    if hypothesis.template_name:
        if "hmac" in hypothesis.template_name:
            return "hmac"
        if "md5" in hypothesis.template_name:
            return "md5"
        if "fingerprint" in hypothesis.template_name:
            return "fingerprint"
    if hypothesis.signature_spec and hypothesis.signature_spec.algorithm_id:
        algo = hypothesis.signature_spec.algorithm_id.lower()
        if algo in {"hmac", "md5", "fingerprint", "rsa", "aes"}:
            return algo
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
    if not dynamic:
        return "(no dynamic hook data)"
    if dynamic.topology_summary:
        return json.dumps(
            {
                "topology_summary": dynamic.topology_summary,
                "bridge_candidates": [item.model_dump(mode="json") for item in dynamic.bridge_candidates[:5]],
            },
            ensure_ascii=False,
            indent=2,
        )
    if not dynamic.hook_intercepts:
        return "(no dynamic hook data)"
    return json.dumps(
        [item.model_dump(mode="json") for item in dynamic.hook_intercepts[:5]],
        ensure_ascii=False,
        indent=2,
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


def _render_base_bridge_template(
    target: TargetSite,
    *,
    hypothesis: AIHypothesis | None = None,
    dynamic: DynamicAnalysis | None = None,
    bridge_port: int,
) -> str:
    raw = BASE_BRIDGE_TEMPLATE.read_text(encoding="utf-8")
    storage_state_path = (
        str(Path(target.session_state.storage_state_path).resolve())
        if target.session_state.storage_state_path
        else ""
    )
    simulation_payload = build_simulation_payload(target.browser_profile)
    executor_candidates = _executor_candidates(dynamic)
    preferred_target = (
        hypothesis.signature_spec.preferred_bridge_target
        if hypothesis and hypothesis.signature_spec and hypothesis.signature_spec.preferred_bridge_target
        else ""
    )
    replacements = {
        "__AXELO_BRIDGE_PORT__": str(bridge_port),
        "__AXELO_START_URL__": json.dumps(target.url or "", ensure_ascii=False),
        "__AXELO_STORAGE_STATE_PATH__": json.dumps(storage_state_path, ensure_ascii=False),
        "__AXELO_DEFAULT_USER_AGENT__": json.dumps(
            _canonical_user_agent(target.browser_profile.user_agent or "")
            or _safe_default_headers(target).get("User-Agent", ""),
            ensure_ascii=False,
        ),
        "__AXELO_DEFAULT_APP_KEY__": json.dumps(_default_app_key(target), ensure_ascii=False),
        "__AXELO_EXECUTOR_CANDIDATES__": json.dumps(executor_candidates, ensure_ascii=False, indent=2),
        "__AXELO_PREFERRED_BRIDGE_TARGET__": json.dumps(preferred_target, ensure_ascii=False),
        "__AXELO_DEFAULT_ENVIRONMENT_SIMULATION__": json.dumps(
            simulation_payload["environmentSimulation"],
            ensure_ascii=False,
            indent=2,
        ),
        "__AXELO_DEFAULT_INTERACTION_SIMULATION__": json.dumps(
            simulation_payload["interactionSimulation"],
            ensure_ascii=False,
            indent=2,
        ),
        "__AXELO_SIMULATION_INIT_SCRIPT_TEMPLATE__": json.dumps(
            SIMULATION_INIT_SCRIPT_TEMPLATE,
            ensure_ascii=False,
        ),
    }
    for placeholder, value in replacements.items():
        raw = raw.replace(placeholder, value)
    return raw


def _render_base_crawler_template(
    target: TargetSite,
    *,
    hypothesis: AIHypothesis | None = None,
    dynamic: DynamicAnalysis | None = None,
    bridge_port: int,
) -> str:
    raw = BASE_CRAWLER_TEMPLATE.read_text(encoding="utf-8")
    storage_state_path = (
        str(Path(target.session_state.storage_state_path).resolve())
        if target.session_state.storage_state_path
        else ""
    )
    simulation_payload = build_simulation_payload(target.browser_profile)
    executor_candidates = _executor_candidates(dynamic)
    preferred_target = (
        hypothesis.signature_spec.preferred_bridge_target
        if hypothesis and hypothesis.signature_spec and hypothesis.signature_spec.preferred_bridge_target
        else ""
    )
    replacements = {
        "__AXELO_CRAWLER_CLASS__": _crawler_class_name(target.url),
        "__AXELO_BRIDGE_PORT__": str(bridge_port),
        "__AXELO_NODE_BIN__": json.dumps(settings.node_bin or "node", ensure_ascii=False),
        "__AXELO_PAGE_ORIGIN__": json.dumps(_page_origin(target.url), ensure_ascii=False),
        "__AXELO_START_URL__": json.dumps(target.url or "", ensure_ascii=False),
        "__AXELO_KNOWN_ENDPOINT__": json.dumps(target.known_endpoint or "", ensure_ascii=False),
        "__AXELO_PREFERRED_API_BASE__": json.dumps(_preferred_api_base(target), ensure_ascii=False),
        "__AXELO_BRIDGE_LOCALE__": json.dumps(target.browser_profile.locale or "en-US", ensure_ascii=False),
        "__AXELO_BRIDGE_TIMEZONE__": json.dumps(target.browser_profile.timezone or "UTC", ensure_ascii=False),
        "__AXELO_STORAGE_STATE_PATH__": json.dumps(storage_state_path, ensure_ascii=False),
        "__AXELO_BRIDGE_TARGETS__": _python_literal(executor_candidates),
        "__AXELO_PREFERRED_BRIDGE_TARGET__": json.dumps(preferred_target, ensure_ascii=False),
        "__AXELO_DEFAULT_HEADERS__": _python_literal(_safe_default_headers(target)),
        "__AXELO_OBSERVED_TARGETS__": _python_literal(_observed_targets_payload(target)),
        "__AXELO_DEFAULT_ENVIRONMENT__": _python_literal(simulation_payload["environmentSimulation"]),
        "__AXELO_DEFAULT_INTERACTION__": _python_literal(simulation_payload["interactionSimulation"]),
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


def _python_literal(value: object) -> str:
    return pformat(value, width=100, sort_dicts=False)


def _crawler_class_name(url: str) -> str:
    host = urlsplit(url).hostname or "generated"
    parts = []
    for chunk in host.split("."):
        cleaned = re.sub(r"[^A-Za-z0-9]+", " ", chunk).strip()
        if not cleaned or cleaned.lower() in {"www", "com", "net", "org"}:
            continue
        parts.append("".join(piece.capitalize() for piece in cleaned.split()))
    return "".join(parts or ["Generated", "Bridge"]) + "Crawler"


def _executor_candidates(dynamic: DynamicAnalysis | None) -> list[dict[str, object]]:
    if not dynamic:
        return []
    candidates = []
    for item in dynamic.bridge_candidates:
        candidates.append(
            {
                "name": item.name,
                "globalPath": item.global_path or None,
                "ownerPath": item.owner_path or None,
                "resolverSource": item.resolver_source or None,
                "resolverArg": {"name": item.name},
                "score": item.score,
                "callable": item.callable,
                "sinkField": item.sink_field,
                "evidenceFrames": item.evidence_frames,
            }
        )
    return candidates


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
    }
    if headers.get("Origin"):
        normalized["Origin"] = headers["Origin"]
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
        if lowered in {"cookie", "content-length", "host", "connection", "accept-encoding", "transfer-encoding"}:
            continue
        if lowered.startswith("sec-"):
            continue
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
        "- Environment simulation is limited to rendering determinism, API availability, and interaction diagnostics.\n"
        "- Challenge and crash states are surfaced back to Python rather than bypassed.\n\n"
        "### Current Session Defaults\n"
        f"- Start URL: `{target.url}`\n"
        f"- Storage state: `{target.session_state.storage_state_path or '(none)'}`\n"
        f"- Bridge port: `{bridge_port}`\n"
        f"- Strategy: `{hypothesis.codegen_strategy}`\n"
        f"- Environment profile: `{target.browser_profile.environment_simulation.profile_name}`\n"
        f"- Interaction mode: `{target.browser_profile.interaction_simulation.mode}`"
    )


def _render_contract_replay_codegen(
    target: TargetSite,
    hypothesis: AIHypothesis,
    dynamic: DynamicAnalysis | None = None,
) -> CodeGenOutput:
    notes = [
        "Contract-backed replay template selected.",
        f"Family: {hypothesis.family_id or 'plain_observed_replay'}",
        f"Strategy: {hypothesis.codegen_strategy}",
    ]
    if hypothesis.codegen_strategy == "js_bridge":
        notes.append(_render_js_bridge_notes(target, hypothesis, bridge_port=8721))
    return CodeGenOutput(
        crawler_code=_render_base_crawler_template(
            target,
            hypothesis=hypothesis,
            dynamic=dynamic,
            bridge_port=8721,
        ),
        dependencies=["httpx>=0.27.0"],
        bridge_server_code="",
        notes="\n".join(notes),
    )


def _build_adapter_package(
    *,
    target: TargetSite,
    hypothesis: AIHypothesis,
    request_contract: RequestContract,
    dataset_contract,
    capability_profile,
    crawler_artifact: str,
    bridge_artifact: str,
    manifest: dict[str, object],
    manifest_ref: str,
) -> AdapterPackage:
    family_id = hypothesis.family_id or (hypothesis.signature_spec.family_id if hypothesis.signature_spec else "unknown")
    verification_profile = VerificationProfile(
        live_verify=target.compliance.allow_live_verification,
        stability_runs=target.compliance.stability_runs,
        failure_modes=[
            "request_shape_mismatch",
            "missing_cookie_or_session",
            "header_contract_mismatch",
            "signature_mismatch",
            "challenge_detected",
            "extractor_mismatch",
            "stability_failure",
        ],
    )
    compatibility_tags = [
        family_id,
        hypothesis.codegen_strategy,
        dataset_contract.dataset_name,
        "verified_candidate",
    ]
    return AdapterPackage(
        site_key=urlsplit(target.url).netloc.lower(),
        intent_fingerprint=target.intent.fingerprint,
        family_id=family_id,
        request_contract_hash=request_contract.contract_hash,
        manifest=manifest,
        request_contract=request_contract,
        signature_spec=hypothesis.signature_spec.model_dump(mode="json") if hypothesis.signature_spec else {},
        capability_profile=capability_profile,
        dataset_contract=dataset_contract,
        crawler_artifact=crawler_artifact,
        bridge_artifact=bridge_artifact,
        verification_profile=verification_profile,
        compatibility_tags=[item for item in compatibility_tags if item],
        source_session_id=target.session_id,
        manifest_ref=manifest_ref,
        created_at=target.created_at,
    )


def _template_is_ready(hypothesis: AIHypothesis, template_item) -> bool:
    if getattr(template_item, "algorithm_type", "") == "fingerprint":
        return True
    return bool(hypothesis.secret_candidate)


def _render_template_codegen(
    template_item,
    target: TargetSite,
    hypothesis: AIHypothesis,
    dynamic: DynamicAnalysis | None = None,
) -> CodeGenOutput:
    if getattr(template_item, "algorithm_type", "") == "fingerprint":
        return CodeGenOutput(
            crawler_code=_render_base_crawler_template(
                target,
                hypothesis=hypothesis,
                dynamic=dynamic,
                bridge_port=8721,
            ),
            dependencies=["curl_cffi>=0.7.0", "httpx>=0.27.0"],
            bridge_server_code="",
            notes=(
                "Template-backed bridge generation selected.\n"
                f"Template: {template_item.name}\n"
                + _render_js_bridge_notes(target, hypothesis, bridge_port=8721)
            ),
        )

    observed = target.target_requests or target.captured_requests
    request = observed[0] if observed else None
    request_url = request.url if request else (target.url or "")
    request_method = request.method if request else "GET"
    request_body = _request_body_to_text(request.request_body) if request else ""
    default_headers = _safe_default_headers(target)
    output_fields = ", ".join(hypothesis.outputs.keys() or ["sign"])

    generator_code = (template_item.python_code or "").strip()
    secret_value = hypothesis.secret_candidate or "CHANGE_ME_SECRET"
    class_name = _crawler_class_name(target.url)
    body_literal = json.dumps(request_body, ensure_ascii=False)
    url_literal = json.dumps(request_url, ensure_ascii=False)
    method_literal = json.dumps(request_method, ensure_ascii=False)
    headers_literal = json.dumps(default_headers, ensure_ascii=False, indent=4)
    token_init = _template_init_expr(template_item, hypothesis)
    sign_kwargs = _template_sign_kwargs(template_item)

    crawler_code = f'''"""
Auto-generated template-backed crawler - Axelo JSReverse
Target: {target.url}
Template: {template_item.name}
"""
import json
from urllib.parse import parse_qsl, urlsplit

try:
    from curl_cffi import requests as _curl_requests
    _TRANSPORT = "curl_cffi"
except ImportError:
    import httpx as _httpx
    _TRANSPORT = "httpx"

{generator_code}


class {class_name}:
    def __init__(self):
        self._last_headers = {{}}
        self._last_request_url = ""
        self._generator = TokenGenerator({token_init})

    def _request_params(self, url: str, body: str) -> dict:
        params = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    params.update({{str(k): str(v) for k, v in payload.items()}})
            except Exception:
                pass
        return params

    def _sign(self, url: str, method: str, body: str) -> dict[str, str]:
        payload = self._generator.generate({sign_kwargs})
        self._last_headers = {{str(k): str(v) for k, v in payload.items()}}
        return self._last_headers

    def crawl(self) -> dict:
        url = {url_literal}
        method = {method_literal}
        body = {body_literal}
        headers = {headers_literal}
        headers.update(self._sign(url, method, body))
        self._last_request_url = url
        if _TRANSPORT == "curl_cffi":
            session = _curl_requests.Session()
            response = session.request(
                method=method,
                url=url,
                headers=headers,
                data=body.encode("utf-8") if body else None,
                timeout=15.0,
                allow_redirects=True,
                impersonate="chrome124",
            )
            session.close()
        else:
            with _httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body.encode("utf-8") if body else None,
                )
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {{
                "status_code": response.status_code,
                "body": response.text,
                "template": {json.dumps(template_item.name, ensure_ascii=False)},
                "expected_fields": {json.dumps(output_fields, ensure_ascii=False)},
            }}


if __name__ == "__main__":
    crawler = {class_name}()
    result = crawler.crawl()
    print(json.dumps(result, ensure_ascii=False, indent=2))
'''
    return CodeGenOutput(
        crawler_code=crawler_code,
        dependencies=["curl_cffi>=0.7.0", "httpx>=0.27.0"],
        bridge_server_code="",
        notes=(
            "Template-backed standalone generation selected.\n"
            f"Template: {template_item.name}\n"
            f"Secret candidate: {secret_value[:24]}"
        ),
    )


def _template_init_expr(template_item, hypothesis: AIHypothesis) -> str:
    algorithm_type = getattr(template_item, "algorithm_type", "")
    secret_value = json.dumps(hypothesis.secret_candidate or "CHANGE_ME_SECRET", ensure_ascii=False)
    if algorithm_type == "hmac":
        return f"secret_key={secret_value}"
    if algorithm_type == "md5":
        return f"salt={secret_value}"
    return ""


def _template_sign_kwargs(template_item) -> str:
    algorithm_type = getattr(template_item, "algorithm_type", "")
    if algorithm_type == "hmac":
        return "url=url, method=method, body=body"
    if algorithm_type == "md5":
        return "params=self._request_params(url, body)"
    return "url=url, method=method, body=body"
