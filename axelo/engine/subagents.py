from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl

from axelo.browser.hooks import DEFAULT_HOOK_TARGETS
from axelo.config import settings
from axelo.engine.executor import ExecutionContext, ToolExecutor
from axelo.memory.db import MemoryDB
from axelo.tools.base import ToolResult, ToolStatus
from axelo.utils.domain import extract_site_domain


ROLE_MAP = {
    "browser": "recon-agent",
    "fetch": "recon-agent",
    "fetch_js_bundles": "recon-agent",
    "memory": "memory-agent",
    "protocol": "transport-agent",
    "runtime_hook": "runtime-agent",
    "critic": "critic-agent",
    "response_schema": "schema-agent",
    "diff": "critic-agent",
    "extraction": "builder-agent",
    "static": "reverse-agent",
    "crypto": "reverse-agent",
    "signature_extractor": "reverse-agent",
    "deobfuscate": "reverse-agent",
    "trace": "reverse-agent",
    "ai_analyze": "reverse-agent",
    "codegen": "builder-agent",
    "verify": "verifier-agent",
}

OBJECTIVE_ROLE_MAP = {
    "discover_surface": "recon-agent",
    "recover_transport": "transport-agent",
    "recover_static_mechanism": "reverse-agent",
    "recover_runtime_mechanism": "runtime-agent",
    "recover_response_schema": "schema-agent",
    "build_artifacts": "builder-agent",
    "verify_execution": "verifier-agent",
    "challenge_findings": "critic-agent",
    "consult_memory": "memory-agent",
}


@dataclass
class AgentDispatchResult:
    tool_name: str
    agent_role: str
    result: ToolResult


class _ScriptSrcCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        src = {key.lower(): value for key, value in attrs}.get("src")
        if src:
            self.sources.append(str(src))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _previous_output(executor: ToolExecutor, tool_name: str) -> dict[str, Any]:
    result = executor.ctx.get_result(tool_name)
    if result and result.success:
        return dict(result.output or {})
    return {}


def _tokenish_fields(payload: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("request_fields", "required_headers", "required_query_fields", "required_body_fields"):
        raw = payload.get(key) or []
        if isinstance(raw, list):
            fields.extend(str(item) for item in raw if item)
    signature_spec = payload.get("signature_spec") or {}
    if isinstance(signature_spec, dict):
        fields.extend(str(item) for item in (signature_spec.get("required_headers") or []) if item)
        fields.extend(str(item) for item in (signature_spec.get("input_fields") or []) if item)
        transport = signature_spec.get("transport_profile") or {}
        if isinstance(transport, dict):
            fields.extend(str(item) for item in (transport.get("request_fields") or []) if item)
    for observed in payload.get("observed_requests") or []:
        if not isinstance(observed, dict):
            continue
        fields.extend(str(key) for key in (observed.get("request_headers") or {}).keys())
        fields.extend(str(key) for key in (observed.get("request_body") or {}).keys())
        fields.extend(key for key, _ in parse_qsl(str(observed.get("url") or "").split("?", 1)[1] if "?" in str(observed.get("url") or "") else ""))
    return _dedupe(fields)


class BaseSubAgent:
    def __init__(self, *, tool_name: str, agent_role: str) -> None:
        self.tool_name = tool_name
        self.agent_role = agent_role

    async def execute(
        self,
        *,
        executor: ToolExecutor,
        initial_input: dict[str, Any],
        task_params: dict[str, Any],
    ) -> ToolResult:
        raise NotImplementedError


class GenericToolSubAgent(BaseSubAgent):
    async def execute(
        self,
        *,
        executor: ToolExecutor,
        initial_input: dict[str, Any],
        task_params: dict[str, Any],
    ) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        return await executor.execute_tool(self.tool_name, payload)


def _select_protocol_request(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[str]], float]:
    requests = [item for item in (payload.get("observed_requests") or []) if isinstance(item, dict)]
    if not requests:
        return {}, {
            "request_fields": _tokenish_fields(payload),
            "all_request_fields": _tokenish_fields(payload),
            "required_headers": [],
            "required_query_fields": [],
            "required_body_fields": [],
            "cookie_fields": [],
            "sensitive_cookies": [],
            "query_fields": [],
            "body_fields": [],
        }, 0.0

    def rank(item: dict[str, Any]) -> float:
        url = str(item.get("url") or "").lower()
        headers = {str(key).lower() for key in (item.get("request_headers") or {}).keys()}
        body = {str(key).lower() for key in (item.get("request_body") or {}).keys()}
        query = {key.lower() for key, _ in parse_qsl(url.split("?", 1)[1] if "?" in url else "")}
        content_type = str((item.get("response_headers") or {}).get("content-type") or "").lower()
        score = 0.0
        if "/api/" in url or "graphql" in url or "search" in url:
            score += 0.45
        if "application/json" in content_type:
            score += 0.2
        if any(token in url for token in ("interstitial", "cart/add", "passport", "login", "qr.", "tracking", "pixel")):
            score -= 0.5
        sensitive = {field for field in headers | body | query if any(token in field for token in ("token", "sign", "csrf", "nonce", "timestamp", "fingerprint", "auth"))}
        score += min(len(sensitive) * 0.06, 0.24)
        return score

    primary = max(requests, key=rank)
    header_keys = [str(key) for key in (primary.get("request_headers") or {}).keys()]
    query_fields = [key for key, _ in parse_qsl(str(primary.get("url") or "").split("?", 1)[1] if "?" in str(primary.get("url") or "") else "")]
    body_fields = [str(key) for key in (primary.get("request_body") or {}).keys()]
    request_fields = _dedupe(_tokenish_fields(payload) + header_keys + query_fields + body_fields)
    return primary, {
        "request_fields": [field for field in request_fields if any(token in field.lower() for token in ("token", "sign", "nonce", "timestamp", "csrf", "fingerprint", "auth"))],
        "all_request_fields": request_fields,
        "required_headers": [field for field in header_keys if any(token in field.lower() for token in ("token", "csrf", "auth", "fingerprint", "x-"))],
        "required_query_fields": [field for field in query_fields if any(token in field.lower() for token in ("sign", "token", "nonce", "timestamp"))],
        "required_body_fields": [field for field in body_fields if any(token in field.lower() for token in ("sign", "token", "nonce", "timestamp", "auth"))],
        "cookie_fields": [],
        "sensitive_cookies": [],
        "query_fields": _dedupe(query_fields),
        "body_fields": _dedupe(body_fields),
    }, rank(primary)


class MemorySubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        url = str(payload.get("target_url") or payload.get("url") or "")
        domain = extract_site_domain(url) or url
        db = MemoryDB(settings.workspace / "memory" / "engine_memory.db")
        similar = [row.model_dump(mode="json") for row in db.get_similar_sessions(domain)[:5]]
        recent = [row.model_dump(mode="json") for row in db.get_recent_sessions(domain, limit=8)]
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "memory_summary": f"Retrieved {len(similar)} verified sessions and {len(recent)} recent sessions for {domain or 'unknown domain'}.",
                "domain": domain,
                "similar_sessions": similar,
                "counterexample_sessions": [row for row in recent if not row.get("verified")][:4],
                "episodic_memory": similar[:3],
                "semantic_memory": [
                    {
                        "pattern_key": f"{row.get('algorithm_type') or 'unknown'}:{row.get('codegen_strategy') or 'unknown'}",
                        "algorithm_type": row.get("algorithm_type") or "unknown",
                        "codegen_strategy": row.get("codegen_strategy") or "unknown",
                    }
                    for row in similar[:3]
                ],
                "confidence": 0.7 if similar else 0.2,
            },
        )


class ProtocolSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        primary, field_summary, surface_rank = _select_protocol_request(payload)
        url = str(primary.get("url") or payload.get("target_url") or payload.get("url") or "")
        method = str(primary.get("method") or "GET").upper()
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "protocol_summary": f"Recovered {method} {url or 'unknown'} with {len(field_summary['request_fields'])} sensitive fields.",
                "target_request_url": url,
                "target_request_method": method,
                "transport_profile": {
                    "url": url,
                    "method": method,
                    "request_fields": field_summary["request_fields"],
                    "query_fields": field_summary["query_fields"],
                    "body_fields": field_summary["body_fields"],
                    "cookie_fields": field_summary["cookie_fields"],
                    "surface_rank": surface_rank,
                },
                "request_fields": field_summary["request_fields"],
                "all_request_fields": field_summary["all_request_fields"],
                "required_headers": field_summary["required_headers"],
                "required_query_fields": field_summary["required_query_fields"],
                "required_body_fields": field_summary["required_body_fields"],
                "sensitive_cookies": field_summary["sensitive_cookies"],
                "surface_rank": surface_rank,
                "counter_surface_hint": "primary_data_surface" if surface_rank >= 0.45 else "config_or_auxiliary",
                "confidence": 0.82 if url else 0.2,
            },
        )


class RuntimeHookSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        fields = [field for field in _tokenish_fields(payload) if any(token in field.lower() for token in ("token", "sign", "nonce", "timestamp", "fingerprint", "auth"))]
        hook_points = ["fetch", "XMLHttpRequest"]
        if any("fingerprint" in field.lower() for field in fields):
            hook_points.extend(["navigator", "canvas", "document.cookie", "localStorage"])
        if any(token in field.lower() for field in fields for token in ("sign", "nonce", "timestamp", "token")):
            hook_points.extend(["crypto.subtle", "Date.now", "Math.random"])
        hook_points = _dedupe(hook_points)
        hook_targets = [target for target in DEFAULT_HOOK_TARGETS if any(point in target for point in hook_points)]
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "hook_summary": f"Prepared runtime hooks for {len(fields)} sensitive fields across {len(hook_points)} hook points.",
                "runtime_sensitive_fields": fields,
                "hook_points": hook_points,
                "hook_targets": hook_targets,
                "hook_script": f"window.__AXELO_HOOK_POINTS__ = {json.dumps(hook_points, ensure_ascii=False)};",
                "hook_executor": {"mode": "browser_init_script", "targets": hook_targets},
                "recommended_next_step": "trace" if fields else "verify",
                "confidence": 0.7 if fields else 0.3,
            },
        )


def _extract_json_samples(payload: dict[str, Any]) -> list[Any]:
    samples: list[Any] = []
    for key in ("response_json", "api_response", "sample_response"):
        value = payload.get(key)
        if value:
            samples.append(value)
    html = str(payload.get("html_content") or "")
    if html:
        for match in re.findall(r"<script[^>]*type=[\"']application/json[\"'][^>]*>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
            try:
                samples.append(json.loads(match))
            except json.JSONDecodeError:
                continue
    return samples


def _flatten_keys(value: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(path)
            keys.extend(_flatten_keys(item, path))
    elif isinstance(value, list) and value:
        keys.extend(_flatten_keys(value[0], prefix))
    return keys


def _select_listing_candidate(samples: list[Any]) -> tuple[list[str], dict[str, Any]]:
    best_fields: list[str] = []
    examples: dict[str, Any] = {}
    for sample in samples:
        stack = [sample]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list) and current and isinstance(current[0], dict):
                fields = list(current[0].keys())
                if len(fields) > len(best_fields):
                    best_fields = fields
                    examples = dict(current[0])
    return best_fields, examples


def _schema_matches(field: str, candidates: list[str]) -> list[str]:
    lowered = field.lower()
    return [candidate for candidate in candidates if lowered in candidate.lower()]


def _dom_candidates_for_field(field: str, html: str) -> list[str]:
    selectors = {
        "title": [".title", "[itemprop='name']", "h3 a", "h2 a"],
        "price": [".price", "[itemprop='price']", ".a-price"],
        "url": ["a[href]"],
        "rating": [".rating", "[itemprop='ratingValue']"],
        "image": ["img[src]", "[itemprop='image']"],
        "review_count": [".review-count", "[itemprop='reviewCount']", ".ratings-count"],
        "brand": [".brand", "[itemprop='brand']", ".product-brand"],
        "category": [".category", "[itemprop='category']", ".breadcrumb"],
        "description": [".description", "[itemprop='description']", ".product-desc"],
        "sku": [".sku", "[itemprop='sku']", ".product-id"],
        "id": ["[data-product-id]", "[data-item-id]", "[data-sku]"],
        "name": [".title", "[itemprop='name']", "h3", "h2"],
    }
    return [selector for selector in selectors.get(field, []) if selector]


def _infer_dom_listing_fields(html: str, goal: str, req_fields: list[str]) -> tuple[list[str], list[str]]:
    """
    Infer listing fields from HTML when no JSON schema is available.
    Returns (listing_item_fields, schema_fields) inferred from DOM patterns and goal.
    This is a generic heuristic — no site-specific logic.
    """
    html_lower = (html or "").lower()
    goal_lower = (goal or "").lower()

    inferred: list[str] = list(req_fields)

    # Goal-based field inference for product/listing intent
    is_listing_goal = any(t in goal_lower for t in (
        "product", "listing", "item", "商品", "列表", "crawl", "extract", "collect", "scrape",
        "price", "rating", "review", "search result",
    ))

    if is_listing_goal or not inferred:
        # Detect field availability from HTML content patterns
        if any(t in html_lower for t in ("price", "$", "€", "¥", "rmb", "usd", "cny", "amount", "cost", "discount")) \
                and "price" not in inferred:
            inferred.append("price")
        if any(t in html_lower for t in ("product", "item", "h2", "h3", "title", "heading", "name")) \
                and "title" not in inferred:
            inferred.append("title")
        if any(t in html_lower for t in ("rating", "star", "review", "score", "feedback")) \
                and "rating" not in inferred:
            inferred.append("rating")
        if any(t in html_lower for t in ("review", "comment", "feedback")) \
                and "review_count" not in inferred:
            inferred.append("review_count")
        if any(t in html_lower for t in ("image", "img", "photo", "picture", "thumbnail")) \
                and "image" not in inferred:
            inferred.append("image")

    # URL is always inferrable from anchor tags
    if "url" not in inferred:
        inferred.append("url")

    inferred = _dedupe(inferred)
    schema_fields = _dedupe(inferred)
    return inferred, schema_fields


class ResponseSchemaSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        samples = _extract_json_samples(payload)
        schema_fields = _dedupe([field for sample in samples for field in _flatten_keys(sample)])[:40]
        listing_item_fields, examples = _select_listing_candidate(samples)
        pagination_fields = [field for field in schema_fields if any(token in field.lower() for token in ("page", "cursor", "offset", "limit"))][:8]

        # When no JSON schema is available, infer listing fields from HTML DOM patterns.
        # This enables the pipeline to proceed to extraction on HTML-rendered listing pages
        # without getting stuck in a schema stall loop.
        dom_inferred = False
        if not listing_item_fields:
            html = str(payload.get("html_content") or "")
            goal = str(payload.get("goal") or "")
            requirements = payload.get("requirements_meta") if isinstance(payload.get("requirements_meta"), dict) else {}
            req_fields = list(requirements.get("fields") or [])
            dom_listing_fields, dom_schema_fields = _infer_dom_listing_fields(html, goal, req_fields)
            if dom_listing_fields:
                listing_item_fields = dom_listing_fields
                schema_fields = _dedupe(schema_fields + dom_schema_fields)
                pagination_fields = [f for f in schema_fields if any(t in f.lower() for t in ("page", "cursor", "offset", "limit"))][:8]
                dom_inferred = True

        response_format = "json" if samples else "html"
        listing_paths = ["embedded_json"] if samples and listing_item_fields else (["dom"] if dom_inferred else [])

        # Provide nested response_schema key so ExtractionSubAgent can access fields directly.
        nested_schema = {
            "schema_fields": schema_fields,
            "listing_item_fields": listing_item_fields,
            "field_examples": examples,
            "listing_paths": listing_paths,
        }

        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "response_schema_summary": f"Recovered {len(schema_fields)} schema fields and {len(listing_item_fields)} listing fields{'(DOM-inferred)' if dom_inferred else ''}.",
                "response_format": response_format,
                "schema_fields": schema_fields,
                "stable_fields": schema_fields[:16],
                "listing_paths": listing_paths,
                "listing_item_fields": listing_item_fields,
                "listing_record_count": 1 if listing_item_fields else 0,
                "field_examples": examples,
                "pagination_fields": pagination_fields,
                "error_patterns": [],
                "confidence": 0.85 if listing_item_fields else 0.4,
                # Nested for downstream ExtractionSubAgent access
                "response_schema": nested_schema,
            },
        )


class DiffSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        observed = [item for item in (payload.get("observed_requests") or []) if isinstance(item, dict)]
        success_cases = [item for item in observed if int(item.get("response_status") or 0) < 400]
        failure_cases = [item for item in observed if int(item.get("response_status") or 0) >= 400]
        changed_headers: list[str] = []
        changed_query_fields: list[str] = []
        if success_cases and failure_cases:
            changed_headers = sorted(set((success_cases[0].get("request_headers") or {}).keys()) ^ set((failure_cases[0].get("request_headers") or {}).keys()))
            changed_query_fields = sorted({key for key, _ in parse_qsl(str(success_cases[0].get("url") or "").split("?", 1)[1] if "?" in str(success_cases[0].get("url") or "") else "")} ^ {key for key, _ in parse_qsl(str(failure_cases[0].get("url") or "").split("?", 1)[1] if "?" in str(failure_cases[0].get("url") or "") else "")})
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "diff_summary": f"Compared {len(success_cases)} success requests and {len(failure_cases)} failure requests.",
                "changed_headers": changed_headers[:20],
                "changed_query_fields": changed_query_fields[:20],
                "changed_cookies": [],
                "recommended_next_step": "recover_transport",
                "confidence": 0.7 if success_cases and failure_cases else 0.2,
            },
        )


class ExtractionSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        requirements = payload.get("requirements_meta") if isinstance(payload.get("requirements_meta"), dict) else {}
        requested_fields = list(requirements.get("fields") or payload.get("fields") or [])
        if not requested_fields:
            requested_fields = ["title", "price", "url"]
        response_schema = payload.get("response_schema") or {}
        if isinstance(response_schema, dict):
            schema_fields = list(response_schema.get("schema_fields") or [])
            listing_item_fields = list(response_schema.get("listing_item_fields") or [])
            field_examples = dict(response_schema.get("field_examples") or {})
        else:
            schema_fields = list(response_schema or [])
            listing_item_fields = []
            field_examples = {}
        candidates = _dedupe(listing_item_fields + schema_fields)
        html = str(payload.get("html_content") or "")
        mapped_fields = []
        covered = 0
        for field in requested_fields:
            api_candidates = _schema_matches(str(field), candidates)
            dom_candidates = _dom_candidates_for_field(str(field).lower(), html)
            resolved_source = "api" if api_candidates else "dom" if dom_candidates else ""
            resolved_path = api_candidates[0] if api_candidates else dom_candidates[0] if dom_candidates else ""
            if resolved_path:
                covered += 1
            mapped_fields.append(
                {
                    "requested_field": field,
                    "api_candidates": api_candidates[:5],
                    "dom_candidates": dom_candidates[:5],
                    "example_value": field_examples.get(str(field)),
                    "resolved_source": resolved_source,
                    "resolved_path": resolved_path,
                    "confidence": 0.85 if resolved_source == "api" else 0.6 if resolved_source == "dom" else 0.0,
                }
            )
        coverage = covered / len(mapped_fields) if mapped_fields else 0.0
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "extraction_summary": f"Mapped {covered}/{len(mapped_fields) or 1} requested fields.",
                "mapped_fields": mapped_fields,
                "source_priority": ["api", "dom"] if candidates else ["dom"],
                "coverage": coverage,
                "requested_fields": requested_fields,
                "confidence": max(coverage, 0.25 if mapped_fields else 0.0),
            },
        )


class CriticSubAgent(BaseSubAgent):
    async def execute(self, *, executor: ToolExecutor, initial_input: dict[str, Any], task_params: dict[str, Any]) -> ToolResult:
        payload = executor._build_input(self.tool_name, initial_input)
        payload.update(task_params)
        verify = _previous_output(executor, "verify")
        protocol = payload.get("protocol_summary") if isinstance(payload.get("protocol_summary"), dict) else _previous_output(executor, "protocol")
        blockers: list[str] = []
        gaps: list[str] = []
        if verify:
            if not bool(verify.get("success")):
                blockers.append("Verification is not passing yet.")
            verdict = str((verify.get("details") or {}).get("mechanism_verdict") or verify.get("mechanism_verdict") or "").lower()
            if verdict in {"", "unknown", "replay_only"}:
                blockers.append("Mechanism closure is still unresolved.")
        if protocol and not (protocol.get("required_headers") or protocol.get("required_query_fields") or protocol.get("required_body_fields")):
            gaps.append("Transport summary still lacks explicit guarded fields.")
        if not blockers and not gaps:
            gaps.append("No critical blocker detected.")
        return ToolResult(
            tool_name=self.tool_name,
            status=ToolStatus.SUCCESS,
            output={
                "critic_summary": f"Critic found {len(blockers)} blockers and {len(gaps)} remaining gaps.",
                "blocking_conditions": blockers,
                "gaps": gaps,
                "non_blocking_gaps": gaps,
                "risks": [],
                "next_probe": "recover_runtime_mechanism" if blockers else "verify_execution",
                "confidence": 0.72 if blockers or gaps else 0.3,
            },
        )


class BaseCapabilityAgent:
    def __init__(self, *, capability: str, agent_role: str) -> None:
        self.capability = capability
        self.agent_role = agent_role

    def plan_actions(self, manager: "SubAgentManager", *, objective: str, task_params: dict[str, Any]) -> list[str]:
        raise NotImplementedError


class SingleToolCapabilityAgent(BaseCapabilityAgent):
    def __init__(self, *, capability: str, agent_role: str, tool_name: str) -> None:
        super().__init__(capability=capability, agent_role=agent_role)
        self.tool_name = tool_name

    def plan_actions(self, manager: "SubAgentManager", *, objective: str, task_params: dict[str, Any]) -> list[str]:
        if self.tool_name == "verify":
            return [self.tool_name]
        return [] if manager._tool_succeeded(self.tool_name) else [self.tool_name]


class ReconCapabilityAgent(BaseCapabilityAgent):
    def plan_actions(self, manager: "SubAgentManager", *, objective: str, task_params: dict[str, Any]) -> list[str]:
        executor = manager._require_executor()
        actions: list[str] = []

        browser_output = manager._result_output("browser")
        fetch_output = manager._result_output("fetch")
        built_browser = executor._build_input("browser", executor.ctx.initial_input)
        built_fetch = executor._build_input("fetch", executor.ctx.initial_input)
        built_bundles = executor._build_input("fetch_js_bundles", executor.ctx.initial_input)

        if not manager._tool_succeeded("browser") and built_browser.get("url"):
            actions.append("browser")
        if not manager._has_surface_evidence(browser_output | fetch_output) and not manager._tool_succeeded("fetch") and built_fetch.get("url"):
            actions.append("fetch")
        if manager._has_bundle_candidates(built_bundles) and not manager._tool_succeeded("fetch_js_bundles"):
            actions.append("fetch_js_bundles")

        if not actions and not manager._has_surface_evidence(browser_output | fetch_output) and built_fetch.get("url"):
            actions.append("fetch")
        return _dedupe(actions)


class ReverseCapabilityAgent(BaseCapabilityAgent):
    def plan_actions(self, manager: "SubAgentManager", *, objective: str, task_params: dict[str, Any]) -> list[str]:
        executor = manager._require_executor()
        actions: list[str] = []

        built_static = executor._build_input("static", executor.ctx.initial_input)
        built_sig = executor._build_input("signature_extractor", executor.ctx.initial_input)
        built_ai = executor._build_input("ai_analyze", executor.ctx.initial_input)
        static_output = manager._result_output("static")
        signature_output = manager._result_output("signature_extractor")

        if manager._has_static_inputs(built_static) and not manager._tool_succeeded("static"):
            actions.append("static")
        if manager._has_signature_inputs(built_sig, static_output) and not manager._tool_succeeded("signature_extractor"):
            actions.append("signature_extractor")
        if manager._has_ai_inputs(built_ai, static_output, signature_output) and not manager._tool_succeeded("ai_analyze"):
            actions.append("ai_analyze")

        if not actions and manager._has_ai_inputs(built_ai, static_output, signature_output):
            actions.append("ai_analyze")
        return _dedupe(actions)


class BuilderCapabilityAgent(BaseCapabilityAgent):
    def plan_actions(self, manager: "SubAgentManager", *, objective: str, task_params: dict[str, Any]) -> list[str]:
        executor = manager._require_executor()
        actions: list[str] = []

        built_extraction = executor._build_input("extraction", executor.ctx.initial_input)
        built_codegen = executor._build_input("codegen", executor.ctx.initial_input)
        extraction_output = manager._result_output("extraction")

        if manager._can_extract(built_extraction) and not manager._tool_succeeded("extraction"):
            actions.append("extraction")
        if manager._can_codegen(built_codegen, extraction_output or built_extraction) and not manager._tool_succeeded("codegen"):
            actions.append("codegen")

        if not actions and not manager._tool_succeeded("codegen") and manager._can_codegen(built_codegen, extraction_output or built_extraction):
            actions.append("codegen")
        return _dedupe(actions)


class SubAgentManager:
    def __init__(self) -> None:
        self._executor: ToolExecutor | None = None
        self._agents: dict[str, BaseSubAgent] = {}
        self._capability_agents: dict[str, BaseCapabilityAgent] = {}
        self._tool_start_callback: Any = None

    def set_tool_start_callback(self, callback: Any) -> None:
        """Callback(tool_name: str) fired just before each tool runs."""
        self._tool_start_callback = callback

    def attach_session(self, *, session_id: str, initial_input: dict[str, Any]) -> None:
        executor = ToolExecutor()
        setattr(executor.state, "session_id", session_id)
        executor.ctx = ExecutionContext(initial_input=initial_input, session_id=session_id)
        self._executor = executor

    def available_objectives(self) -> list[str]:
        return list(OBJECTIVE_ROLE_MAP.keys())

    def register(self, agent: BaseSubAgent) -> None:
        self._agents[agent.tool_name] = agent

    def ensure_default_agents(self, tool_names: list[str]) -> None:
        for tool_name in tool_names:
            if tool_name not in self._agents:
                self._agents[tool_name] = self._build_agent(tool_name)

    def agent_role_for(self, tool_name: str) -> str:
        return self._agents.get(tool_name, self._build_agent(tool_name)).agent_role

    async def execute_task(self, *, tool_name: str, initial_input: dict[str, Any], task_params: dict[str, Any]) -> AgentDispatchResult:
        if self._executor is None:
            raise RuntimeError("SubAgentManager session not attached")
        agent = self._agents.get(tool_name)
        if agent is None:
            agent = self._build_agent(tool_name)
            self._agents[tool_name] = agent
        if self._tool_start_callback:
            self._tool_start_callback(tool_name)
        result = await agent.execute(executor=self._executor, initial_input=initial_input, task_params=task_params)
        if result.success:
            self._executor.state.save_result(result)
            self._executor.ctx.add_result(tool_name, result)
        return AgentDispatchResult(tool_name=tool_name, agent_role=agent.agent_role, result=result)

    async def execute_objective(self, *, objective: str, objective_id: str, initial_input: dict[str, Any], task_params: dict[str, Any]):
        from axelo.engine.models import AgentReport, EvidenceRecord, now_iso

        started = time.monotonic()
        tool_results: dict[str, dict[str, Any]] = {}
        evidence: list[EvidenceRecord] = []
        claims: list[str] = []
        questions: list[str] = []
        counterevidence: list[str] = []
        success = True
        executed_tools: list[str] = []

        capability_agent = self._capability_agent_for(objective)
        while True:
            next_actions = [
                tool_name
                for tool_name in capability_agent.plan_actions(self, objective=objective, task_params=task_params)
                if tool_name not in executed_tools
            ]
            if not next_actions:
                break
            tool_name = next_actions[0]
            executed_tools.append(tool_name)
            dispatch = await self.execute_task(tool_name=tool_name, initial_input=initial_input, task_params=task_params)
            result = dispatch.result
            tool_results[tool_name] = dict(result.output or {})
            summary = self._claim_from_output(tool_name, result.output or {})
            if summary:
                claims.append(summary)
            question = self._question_from_output(result.output or {})
            if question:
                questions.append(question)
            evidence.append(
                EvidenceRecord(
                    evidence_id=f"{objective_id}:{tool_name}:{int(time.time() * 1000)}",
                    kind=tool_name,
                    source_task=objective_id,
                    summary=summary or f"{tool_name} {'succeeded' if result.success else 'failed'}.",
                    confidence=float((result.output or {}).get("confidence") or (result.output or {}).get("score") or (0.8 if result.success else 0.2)),
                    details=dict(result.output or {}),
                    created_at=now_iso(),
                )
            )
            if not result.success:
                success = False
                if result.error:
                    counterevidence.append(result.error)
                if not (objective == "discover_surface" and tool_name == "browser"):
                    break

        if not executed_tools:
            success = False
            counterevidence.append("No actionable tool path was selected for this objective.")

        return AgentReport(
            run_id=f"{objective_id}:{int(time.time() * 1000)}",
            objective_id=objective_id,
            objective=objective,
            capability=capability_agent.capability,
            agent_role=capability_agent.agent_role,
            success=success,
            summary=f"{objective} {'completed' if success else 'stalled'} using {', '.join(tool_results) or 'no tools'}.",
            claims=_dedupe(claims),
            counterevidence=_dedupe(counterevidence),
            evidence=evidence,
            outputs=self._aggregate_outputs(tool_results),
            tool_results=tool_results,
            recommended_questions=_dedupe(questions),
            duration_seconds=time.monotonic() - started,
            created_at=now_iso(),
        )

    def _build_agent(self, tool_name: str) -> BaseSubAgent:
        factories: dict[str, type[BaseSubAgent]] = {
            "memory": MemorySubAgent,
            "protocol": ProtocolSubAgent,
            "runtime_hook": RuntimeHookSubAgent,
            "response_schema": ResponseSchemaSubAgent,
            "diff": DiffSubAgent,
            "extraction": ExtractionSubAgent,
            "critic": CriticSubAgent,
        }
        agent_cls = factories.get(tool_name, GenericToolSubAgent)
        return agent_cls(tool_name=tool_name, agent_role=ROLE_MAP.get(tool_name, f"{tool_name}-agent"))

    def _capability_agent_for(self, objective: str) -> BaseCapabilityAgent:
        capability = self._capability_for_objective(objective)
        if capability not in self._capability_agents:
            self._capability_agents[capability] = self._build_capability_agent(objective, capability)
        return self._capability_agents[capability]

    def _build_capability_agent(self, objective: str, capability: str) -> BaseCapabilityAgent:
        if capability == "recon":
            return ReconCapabilityAgent(capability=capability, agent_role=OBJECTIVE_ROLE_MAP.get(objective, "recon-agent"))
        if capability == "reverse":
            return ReverseCapabilityAgent(capability=capability, agent_role=OBJECTIVE_ROLE_MAP.get(objective, "reverse-agent"))
        if capability == "builder":
            return BuilderCapabilityAgent(capability=capability, agent_role=OBJECTIVE_ROLE_MAP.get(objective, "builder-agent"))
        single_tool = {
            "transport": "protocol",
            "runtime": "runtime_hook",
            "schema": "response_schema",
            "verifier": "verify",
            "critic": "critic",
            "memory": "memory",
        }.get(capability)
        if single_tool:
            return SingleToolCapabilityAgent(
                capability=capability,
                agent_role=OBJECTIVE_ROLE_MAP.get(objective, f"{capability}-agent"),
                tool_name=single_tool,
            )
        return SingleToolCapabilityAgent(
            capability=capability,
            agent_role=OBJECTIVE_ROLE_MAP.get(objective, "general-agent"),
            tool_name="critic",
        )

    def _capability_for_objective(self, objective: str) -> str:
        return {
            "discover_surface": "recon",
            "recover_transport": "transport",
            "recover_static_mechanism": "reverse",
            "recover_runtime_mechanism": "runtime",
            "recover_response_schema": "schema",
            "build_artifacts": "builder",
            "verify_execution": "verifier",
            "challenge_findings": "critic",
            "consult_memory": "memory",
        }.get(objective, "general")

    def _require_executor(self) -> ToolExecutor:
        if self._executor is None:
            raise RuntimeError("SubAgentManager session not attached")
        return self._executor

    def _tool_succeeded(self, tool_name: str) -> bool:
        executor = self._require_executor()
        existing = executor.ctx.get_result(tool_name)
        return bool(existing and existing.success)

    def _result_output(self, tool_name: str) -> dict[str, Any]:
        executor = self._require_executor()
        existing = executor.ctx.get_result(tool_name)
        if existing and existing.success:
            return dict(existing.output or {})
        return {}

    @staticmethod
    def _has_surface_evidence(payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("page_title")
            or payload.get("page_url")
            or payload.get("html_content")
            or payload.get("content")
            or payload.get("observed_requests")
        )

    @staticmethod
    def _has_bundle_candidates(payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("js_urls")
            or payload.get("js_bundles")
            or payload.get("urls")
            or payload.get("bundles")
        )

    @staticmethod
    def _has_static_inputs(payload: dict[str, Any]) -> bool:
        return bool(payload.get("js_code") or payload.get("bundles") or payload.get("content"))

    @staticmethod
    def _has_signature_inputs(payload: dict[str, Any], static_output: dict[str, Any]) -> bool:
        return bool(
            payload.get("js_code")
            or payload.get("api_endpoints")
            or payload.get("endpoints")
            or payload.get("candidates")
            or static_output.get("api_endpoints")
            or static_output.get("endpoints")
            or static_output.get("token_candidates")
        )

    @staticmethod
    def _has_ai_inputs(payload: dict[str, Any], static_output: dict[str, Any], signature_output: dict[str, Any]) -> bool:
        return bool(
            payload.get("js_code")
            or payload.get("signature_extraction")
            or payload.get("signature_spec")
            or payload.get("candidates")
            or static_output
            or signature_output
        )

    @staticmethod
    def _can_extract(payload: dict[str, Any]) -> bool:
        response_schema = payload.get("response_schema") or {}
        if isinstance(response_schema, dict):
            schema_fields = response_schema.get("schema_fields") or []
            listing_fields = response_schema.get("listing_item_fields") or []
            if schema_fields or listing_fields:
                return True
        return bool(
            payload.get("schema_fields")
            or payload.get("listing_item_fields")
            or payload.get("html_content")
            or payload.get("response_json")
            or payload.get("api_response")
            or payload.get("sample_response")
        )

    @staticmethod
    def _can_codegen(payload: dict[str, Any], extraction_output: dict[str, Any]) -> bool:
        coverage = 0.0
        if isinstance(extraction_output, dict):
            coverage = float(extraction_output.get("coverage") or 0.0)
        return bool(
            coverage > 0.0
            or payload.get("signature_spec")
            or payload.get("signature_spec_model")
            or payload.get("target_requests")
            or payload.get("captured_requests")
        ) and bool(payload.get("target_url") or payload.get("url") or payload.get("page_url"))

    def _aggregate_outputs(self, tool_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for tool_name, output in tool_results.items():
            merged[tool_name] = output
            for key, value in output.items():
                merged.setdefault(key, value)
        return merged

    def _claim_from_output(self, tool_name: str, output: dict[str, Any]) -> str:
        for key in (
            "memory_summary",
            "protocol_summary",
            "hook_summary",
            "response_schema_summary",
            "diff_summary",
            "extraction_summary",
            "critic_summary",
            "summary",
            "report",
        ):
            text = str(output.get(key) or "").strip()
            if text:
                return text
        if tool_name == "verify" and output.get("success"):
            return "Verification produced a passing execution result."
        return ""

    def _question_from_output(self, output: dict[str, Any]) -> str:
        for key in ("recommended_next_step", "next_probe", "retry_strategy"):
            value = str(output.get(key) or "").strip()
            if value:
                return f"Investigate {value} next."
        return ""
