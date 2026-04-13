"""
Code generation tool.

Builds crawler code from a canonical signature specification and extracted
evidence. This tool is intentionally conservative: it prefers structured
inputs and publishes a canonical crawler source object for downstream verify.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import structlog

from axelo.config import settings
from axelo.models.signature import SignatureSpec
from axelo.models.target import RequestCapture
from axelo.tools.base import (
    BaseTool,
    ToolCategory,
    ToolInput,
    ToolOutput,
    ToolResult,
    ToolSchema,
    ToolState,
    ToolStatus,
    get_registry,
)

log = structlog.get_logger()


@dataclass
class CodegenOutput:
    python_code: str = ""
    js_code: str = ""
    requirements: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


class CodegenTool(BaseTool):
    @property
    def name(self) -> str:
        return "codegen"

    @property
    def description(self) -> str:
        return "Generate crawler code from structured reverse-engineering results."

    def _create_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            category=ToolCategory.CODEGEN,
            input_schema=[
                ToolInput(name="hypothesis", type="string", description="Signature hypothesis", required=False),
                ToolInput(name="signature_type", type="string", description="Signature family", required=False),
                ToolInput(name="algorithm", type="string", description="Algorithm identifier", required=False),
                ToolInput(name="target_url", type="string", description="Target URL", required=True),
                ToolInput(name="key_location", type="string", description="Key origin hint", required=False),
                ToolInput(name="extracted_key", type="object", description="Extracted key metadata", required=False),
                ToolInput(name="signature_spec", type="object", description="Canonical signature specification", required=False),
                ToolInput(name="target_requests", type="array", description="Observed browser/network requests", required=False),
                ToolInput(name="output_format", type="string", description="python, js, both", required=False, default="python"),
            ],
            output_schema=[
                ToolOutput(name="python_code", type="string", description="Python crawler code"),
                ToolOutput(name="js_code", type="string", description="JavaScript bridge code"),
                ToolOutput(name="requirements", type="array", description="Dependency list"),
                ToolOutput(name="manifest", type="object", description="Generation manifest"),
                ToolOutput(name="crawler_source", type="object", description="Canonical crawler source"),
            ],
            timeout_seconds=120,
            retry_enabled=True,
            max_retries=2,
        )

    async def execute(self, input_data: dict[str, Any], state: ToolState) -> ToolResult:
        signature_spec = self._coerce_signature_spec(
            input_data.get("signature_spec_model") or input_data.get("signature_spec")
        )
        hypothesis = input_data.get("hypothesis") or self._derive_hypothesis(signature_spec)
        target_url = input_data.get("target_url") or input_data.get("page_url") or input_data.get("url")

        if not hypothesis and signature_spec is None:
            # Allow page-extract generation for HTML listing targets without hypothesis/spec.
            # The _generate() method will route to the page_extract path automatically.
            goal = input_data.get("goal", "")
            if not (target_url and self._looks_html_listing_target(target_url, goal)):
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error="Missing required input: hypothesis or signature_spec",
                )
        if not target_url:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error="Missing required input: target_url",
            )

        try:
            output = self._generate(input_data)
            log.info(
                "codegen_debug",
                has_python_code=bool(output.python_code),
                code_length=len(output.python_code) if output.python_code else 0,
                has_js_code=bool(output.js_code),
            )

            session_id = getattr(state, "session_id", None)
            if session_id:
                session_dir = settings.session_dir(session_id)
                session_dir.mkdir(parents=True, exist_ok=True)
                if output.python_code:
                    (session_dir / "crawler.py").write_text(output.python_code, encoding="utf-8")
                if output.js_code:
                    (session_dir / "signature.js").write_text(output.js_code, encoding="utf-8")
                if output.manifest:
                    (session_dir / "manifest.json").write_text(
                        json.dumps(output.manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                log.info("codegen_artifacts_saved", session=session_id, files=["crawler.py", "signature.js", "manifest.json"])

            safe_algorithm = self._ascii_safe(input_data.get("algorithm", "unknown"))
            log.info("codegen_success", url=target_url, algorithm=safe_algorithm)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={
                    "python_code": output.python_code,
                    "js_code": output.js_code,
                    "requirements": output.requirements,
                    "manifest": output.manifest,
                    "crawler_source": {
                        "source": "codegen_tool",
                        "python_code": output.python_code,
                        "js_code": output.js_code,
                        "strategy_used": output.manifest.get("generation_mode") if isinstance(output.manifest, dict) else "",
                    },
                },
            )
        except Exception as exc:
            log.error("codegen_tool_failed", error=str(exc))
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(exc),
            )

    @staticmethod
    def _ascii_safe(value: Any) -> str:
        text = str(value) if value is not None else ""
        return text.encode("ascii", errors="backslashreplace").decode("ascii")

    @staticmethod
    def _coerce_signature_spec(candidate: Any) -> SignatureSpec | None:
        if isinstance(candidate, SignatureSpec):
            return candidate
        if isinstance(candidate, dict) and candidate:
            try:
                return SignatureSpec.model_validate(candidate)
            except Exception:
                return None
        return None

    @staticmethod
    def _derive_hypothesis(signature_spec: SignatureSpec | None) -> str:
        if signature_spec is None:
            return ""
        step_text = ", ".join(signature_spec.canonical_steps) or signature_spec.algorithm_id or "unknown"
        return f"Reconstruct {signature_spec.family_id} signing flow using canonical steps: {step_text}."

    def _generate(self, input_data: dict[str, Any]) -> CodegenOutput:
        output = CodegenOutput()
        signature_spec = self._coerce_signature_spec(
            input_data.get("signature_spec_model") or input_data.get("signature_spec")
        )

        algorithm = input_data.get("algorithm") or (signature_spec.algorithm_id if signature_spec else "unknown")
        signature_type = input_data.get("signature_type") or (signature_spec.family_id if signature_spec else "")
        target_url = input_data.get("target_url") or input_data.get("url") or input_data.get("page_url") or ""
        key_location = input_data.get("key_location") or (
            signature_spec.preferred_bridge_target if signature_spec and signature_spec.preferred_bridge_target else ""
        )
        output_format = input_data.get("output_format", "python")
        hypothesis = input_data.get("hypothesis") or self._derive_hypothesis(signature_spec)
        api_endpoints = input_data.get("api_endpoints") or input_data.get("endpoints") or []
        if not api_endpoints and signature_spec and signature_spec.transport_profile.get("url_pattern"):
            api_endpoints = [signature_spec.transport_profile["url_pattern"]]
        extracted_key = input_data.get("extracted_key")
        target_requests = self._coerce_requests(input_data.get("target_requests") or input_data.get("captures"))
        cookies = self._coerce_cookies(input_data.get("cookies"))
        codegen_strategy = signature_spec.codegen_strategy if signature_spec else ""

        if self._should_generate_page_extract(
            target_url=target_url,
            goal=input_data.get("goal", ""),
            signature_spec=signature_spec,
            extracted_key=extracted_key,
            target_requests=target_requests,
        ):
            output.python_code = self._generate_page_extract_python_v2(target_url)
            output.js_code = ""
            output.requirements = ["httpx>=0.27.0", "playwright>=1.48.0"]
            output.manifest = {
                "target_url": target_url,
                "signature_type": signature_type,
                "algorithm": algorithm,
                "key_location": key_location,
                "hypothesis": hypothesis[:200],
                "output_format": "python",
                "generated_at": "2026-04-11",
                "signature_spec": signature_spec.model_dump(mode="json") if signature_spec else {},
                "requires_manual_key": False,
                "generation_mode": "page_extract",
            }
            return output

        if codegen_strategy == "observed_replay" and target_requests:
            observed_request = self._select_observed_request(target_requests, signature_spec)
            output.python_code = self._generate_observed_replay_python(
                target_url,
                target_requests,
                signature_spec,
                cookies,
            )
            output.js_code = ""
            output.requirements = ["httpx>=0.27.0", "playwright>=1.48.0"]
            output.manifest = {
                "target_url": target_url,
                "signature_type": signature_type,
                "algorithm": algorithm,
                "key_location": key_location,
                "hypothesis": hypothesis[:200],
                "output_format": "python",
                "generated_at": "2026-04-11",
                "signature_spec": signature_spec.model_dump(mode="json") if signature_spec else {},
                "requires_manual_key": False,
                "generation_mode": "observed_replay",
                "observed_request_url": observed_request.url,
                "observed_request_method": observed_request.method,
                "observed_cookie_count": len(cookies),
            }
            return output

        if output_format in ("python", "both"):
            output.python_code = self._generate_python(
                target_url,
                algorithm,
                signature_type,
                key_location,
                hypothesis,
                api_endpoints,
                extracted_key,
                signature_spec,
            )
        if output_format in ("js", "both"):
            output.js_code = self._generate_js(
                target_url,
                algorithm,
                signature_type,
                key_location,
                signature_spec,
            )

        output.requirements = ["httpx>=0.27.0", "playwright>=1.48.0"]
        algos_lower = str(algorithm or "").lower()
        if any(token in algos_lower for token in ("aes", "rsa", "hmac")):
            output.requirements.append("pycryptodome>=3.18.0")

        output.manifest = {
            "target_url": target_url,
            "signature_type": signature_type,
            "algorithm": algorithm,
            "key_location": key_location,
            "hypothesis": hypothesis[:200],
            "output_format": output_format,
            "generated_at": "2026-04-11",
            "signature_spec": signature_spec.model_dump(mode="json") if signature_spec else {},
            "requires_manual_key": not bool(extracted_key and extracted_key.get("key_value")),
        }
        return output

    def _generate_page_extract_python_v2(self, url: str) -> str:
        return f'''"""
Page extraction crawler for {url}
Generated by Axelo unified engine

Strategy:
- generation_mode: page_extract
- purpose: collect listing data directly from the rendered page when reverse evidence is too weak
"""

import asyncio
import json
import re
import sys
from html import unescape
from urllib.parse import urljoin

# Ensure stdout can handle Unicode on all platforms (Windows CP1252, etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from playwright.async_api import async_playwright


TARGET_URL = {json.dumps(url, ensure_ascii=False)}
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HTML_HEADERS = {{
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}}
PRICE_REGEX = re.compile(r"(?:[$€£¥]|RM|Rp|IDR|CNY|RMB|NT\\$|₱)\\s*\\d[\\d.,]*", re.IGNORECASE)
TAG_REGEX = re.compile(r"<[^>]+>")
ANCHOR_REGEX = re.compile(r'<a[^>]+href=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
IMAGE_REGEX = re.compile(r'<img[^>]+src=["\\\']([^"\\\']+)["\\\']', re.IGNORECASE)
WHITESPACE_REGEX = re.compile(r"\\s+")


def _clean_html_text(value: str) -> str:
    text = TAG_REGEX.sub(" ", value or "")
    return WHITESPACE_REGEX.sub(" ", unescape(text)).strip()


def extract_listing_items_from_html(html_text: str, base_url: str) -> list[dict]:
    results = []
    seen = set()
    for match in ANCHOR_REGEX.finditer(html_text or ""):
        href, inner = match.groups()
        href = (href or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        text = _clean_html_text(inner)
        if len(text) < 8:
            continue
        snippet_start = max(0, match.start() - 240)
        snippet_end = min(len(html_text), match.end() + 240)
        snippet = html_text[snippet_start:snippet_end]
        snippet_text = _clean_html_text(snippet)
        price_match = PRICE_REGEX.search(snippet_text)
        image_match = IMAGE_REGEX.search(snippet)
        key = f"{{text}}@@{{full_url}}"
        if key in seen:
            continue
        seen.add(key)
        results.append({{
            "title": text,
            "url": full_url,
            "price": price_match.group(0) if price_match else "",
            "image": image_match.group(1) if image_match else "",
        }})
        if len(results) >= 25:
            break
    return results


async def extract_via_httpx() -> dict:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HTML_HEADERS) as client:
        response = await client.get(TARGET_URL)
        html_text = response.text or ""
        items = extract_listing_items_from_html(html_text, TARGET_URL)
        return {{
            "status": response.status_code,
            "items": items,
            "item_count": len(items),
            "mode": "httpx_html",
        }}


async def extract_via_browser() -> dict:
    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_USER_AGENT)
            page = await context.new_page()
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
            html_text = await page.content()
            items = extract_listing_items_from_html(html_text, TARGET_URL)
            return {{
                "status": 200,
                "items": items,
                "item_count": len(items),
                "mode": "playwright_html",
            }}
    finally:
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()


async def main():
    result = {{
        "status": 0,
        "items": [],
        "item_count": 0,
        "mode": "none",
    }}
    try:
        result = await extract_via_httpx()
    except Exception as exc:
        result["httpx_error"] = str(exc)
    if result.get("item_count", 0) < 5:
        try:
            browser_result = await extract_via_browser()
            if browser_result.get("item_count", 0) >= result.get("item_count", 0):
                result = browser_result
        except Exception as exc:
            result["browser_error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
'''

    @staticmethod
    def _looks_html_listing_target(target_url: str, goal: str = "") -> bool:
        """
        Return True when the target is an HTML listing/search page and not a raw API endpoint.
        Checks both URL patterns and the crawl goal so that homepage-style URLs with a
        product-crawl objective are still classified correctly.
        """
        lowered = str(target_url or "").lower()
        if "/api/" in lowered or "/graphql" in lowered:
            return False
        # URL-pattern detection
        if any(term in lowered for term in (
            "search", "listing", "catalog", "product", "search_result",
            "q=", "keyword=", "search_key=", "wd=", "query=",
        )):
            return True
        # Goal-based detection: any crawl / extraction intent on a non-API URL
        goal_lower = (goal or "").lower()
        return any(term in goal_lower for term in (
            "crawl", "listing", "product", "items", "extract", "collect", "scrape",
            "商品", "清单", "列表", "爬取", "抓取", "数据采集",
        ))

    @staticmethod
    def _observed_request_is_auxiliary(request: RequestCapture | None) -> bool:
        if request is None:
            return False
        lowered = str(request.url or "").lower()
        if lowered.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".webp")):
            return True
        auxiliary_terms = (
            "captcha",
            "verify",
            "verification",
            "challenge",
            "passport",
            "sso",
            "collect",
            "telemetry",
            "metric",
            "analytics",
            "doubleclick",
            "googleadservices",
            "gstatic",
            "/adx/",
            "/cm/",
            "/ttc",
            "/setting/",
            "/config",
        )
        return any(term in lowered for term in auxiliary_terms)

    @staticmethod
    def _has_grounded_key(extracted_key: dict[str, Any] | None) -> bool:
        if not extracted_key or not extracted_key.get("key_value"):
            return False
        value = str(extracted_key.get("key_value") or "").strip()
        if len(value) < 10:
            return False
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{8,}", value) and not any(ch.isdigit() for ch in value):
            return False
        return True

    def _should_generate_page_extract(
        self,
        *,
        target_url: str,
        goal: str = "",
        signature_spec: SignatureSpec | None,
        extracted_key: dict[str, Any] | None,
        target_requests: list[RequestCapture],
    ) -> bool:
        if not self._looks_html_listing_target(target_url, goal):
            return False
        if self._has_grounded_key(extracted_key):
            return False
        if signature_spec is None:
            return True
        if signature_spec.codegen_strategy == "js_bridge":
            return False
        mechanism_fields = (
            list(signature_spec.signature_fields.keys())
            + list(signature_spec.fingerprint_fields.keys())
            + list(signature_spec.runtime_token_fields.keys())
            + list(signature_spec.signing_inputs)
        )
        required_headers = list(signature_spec.header_policy.get("required", []) if signature_spec.header_policy else [])
        query_fields = list(signature_spec.transport_profile.get("query_fields", []) if signature_spec.transport_profile else [])
        body_fields = list(signature_spec.transport_profile.get("body_fields", []) if signature_spec.transport_profile else [])
        weak_spec = (
            (signature_spec.algorithm_id in {"", "unknown"} and not required_headers and not mechanism_fields)
            or (not mechanism_fields and not required_headers)
            or (signature_spec.algorithm_id in {"", "unknown"} and not self._has_grounded_key(extracted_key))
        )
        if signature_spec.codegen_strategy == "observed_replay" and target_requests:
            observed = self._select_observed_request(target_requests, signature_spec)
            replay_surface_is_auxiliary = self._observed_request_is_auxiliary(observed)
            no_structured_contract = not query_fields and not body_fields
            if replay_surface_is_auxiliary and no_structured_contract and not self._has_grounded_key(extracted_key):
                return True
            return False
        return weak_spec

    @staticmethod
    def _coerce_requests(value: Any) -> list[RequestCapture]:
        if not isinstance(value, list):
            return []
        requests: list[RequestCapture] = []
        for item in value:
            try:
                if isinstance(item, RequestCapture):
                    requests.append(item)
                elif isinstance(item, dict) and item.get("url"):
                    requests.append(RequestCapture.model_validate(item))
            except Exception:
                continue
        return requests

    @staticmethod
    def _filter_observed_headers(headers: dict[str, str]) -> dict[str, str]:
        filtered: dict[str, str] = {}
        for key, value in (headers or {}).items():
            lowered = str(key).lower()
            if not value:
                continue
            if lowered in {"cookie", "content-length", "host", "connection", "accept-encoding", "transfer-encoding"}:
                continue
            if lowered.startswith("sec-"):
                continue
            filtered[str(key)] = str(value)
        return filtered

    @staticmethod
    def _coerce_cookies(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        cookies: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict) and item.get("name") and "value" in item:
                cookies.append(dict(item))
        return cookies

    @staticmethod
    def _cookies_for_request(cookies: list[dict[str, Any]], request_url: str) -> dict[str, str]:
        host = urlsplit(request_url).hostname or ""
        if not host:
            return {}
        selected: dict[str, str] = {}
        for cookie in cookies:
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            domain = str(cookie.get("domain") or "").lstrip(".").lower()
            if not name:
                continue
            if domain and not (host == domain or host.endswith(f".{domain}") or domain.endswith(host)):
                continue
            selected[name] = value
        return selected

    @staticmethod
    def _playwright_cookies_for_request(cookies: list[dict[str, Any]], request_url: str) -> list[dict[str, Any]]:
        host = urlsplit(request_url).hostname or ""
        if not host:
            return []
        selected: list[dict[str, Any]] = []
        for cookie in cookies:
            name = str(cookie.get("name") or "").strip()
            value = str(cookie.get("value") or "")
            domain = str(cookie.get("domain") or "").strip()
            normalized_domain = domain.lstrip(".").lower()
            if not name:
                continue
            if normalized_domain and not (host == normalized_domain or host.endswith(f".{normalized_domain}") or normalized_domain.endswith(host)):
                continue
            payload: dict[str, Any] = {
                "name": name,
                "value": value,
                "domain": domain or host,
                "path": str(cookie.get("path") or "/"),
                "httpOnly": bool(cookie.get("httpOnly") or False),
                "secure": bool(cookie.get("secure") or False),
            }
            same_site = str(cookie.get("sameSite") or "").strip()
            if same_site in {"Strict", "Lax", "None"}:
                payload["sameSite"] = same_site
            expires = cookie.get("expires")
            if isinstance(expires, (int, float)) and float(expires) > 0:
                payload["expires"] = int(float(expires))
            selected.append(payload)
        return selected

    @staticmethod
    def _browser_replay_headers(headers: dict[str, str]) -> dict[str, str]:
        filtered: dict[str, str] = {}
        forbidden = {
            "user-agent",
            "referer",
            "origin",
            "cookie",
            "content-length",
            "accept-encoding",
            "host",
            "connection",
            "sec-fetch-site",
            "sec-fetch-mode",
            "sec-fetch-dest",
            "sec-fetch-user",
        }
        for key, value in (headers or {}).items():
            lowered = str(key).lower()
            if lowered in forbidden or lowered.startswith("sec-"):
                continue
            filtered[str(key)] = str(value)
        return filtered

    @staticmethod
    def _request_body_literal(body: bytes | None) -> str:
        if not body:
            return '""'
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            decoded = body.decode("utf-8", errors="replace")
        return json.dumps(decoded, ensure_ascii=False)

    def _generate_observed_replay_python(
        self,
        target_url: str,
        target_requests: list[RequestCapture],
        signature_spec: SignatureSpec | None,
        cookies: list[dict[str, Any]],
    ) -> str:
        primary = self._select_observed_request(target_requests, signature_spec)
        observed_headers = self._filter_observed_headers(primary.request_headers)
        observed_headers_literal = repr(observed_headers)
        observed_cookies = self._cookies_for_request(cookies, primary.url)
        observed_cookies_literal = repr(observed_cookies)
        observed_playwright_cookies = self._playwright_cookies_for_request(cookies, primary.url)
        observed_playwright_cookies_literal = repr(observed_playwright_cookies)
        observed_browser_headers = self._browser_replay_headers(observed_headers)
        observed_browser_headers_literal = repr(observed_browser_headers)
        request_body_literal = self._request_body_literal(primary.request_body)
        output_fields = list((signature_spec.signing_outputs or signature_spec.output_fields).keys()) if signature_spec else []
        required_headers = signature_spec.header_policy.get("required", []) if signature_spec and signature_spec.header_policy else []
        required_header_names = self._required_header_names(signature_spec)
        required_header_names_literal = repr(required_header_names)
        sign_note = ", ".join(output_fields or required_headers or ["(none)"])
        browser_user_agent = str(primary.request_headers.get("user-agent") or "")

        return f'''"""
Observed replay crawler for {target_url}
Generated by Axelo unified engine

Strategy:
- generation_mode: observed_replay
- observed_request: {primary.method} {primary.url}
- required_signature_or_runtime_fields: {sign_note}

This crawler replays the most relevant observed request instead of inventing a
crypto primitive that was not recovered from evidence.
"""

import asyncio
import json

import httpx
from playwright.async_api import async_playwright


TARGET_PAGE_URL = {json.dumps(target_url, ensure_ascii=False)}
OBSERVED_URL = {json.dumps(primary.url, ensure_ascii=False)}
OBSERVED_METHOD = {json.dumps(primary.method.upper(), ensure_ascii=False)}
OBSERVED_HEADERS = {observed_headers_literal}
OBSERVED_BROWSER_HEADERS = {observed_browser_headers_literal}
OBSERVED_COOKIES = {observed_cookies_literal}
OBSERVED_PLAYWRIGHT_COOKIES = {observed_playwright_cookies_literal}
OBSERVED_BODY = {request_body_literal}
BROWSER_USER_AGENT = {json.dumps(browser_user_agent, ensure_ascii=False)}
REQUIRED_SPEC_HEADERS = {required_header_names_literal}


def _guess_required_header_value(name: str) -> str:
    lowered = (name or "").lower()
    if "fingerprint" in lowered:
        return "|".join(
            part for part in (
                BROWSER_USER_AGENT,
                "1920x1080",
                "zh-CN",
                TARGET_PAGE_URL,
            )
            if part
        )
    if "token" in lowered or "nonce" in lowered or "csrf" in lowered:
        return "observed-runtime-required"
    if "signature" in lowered:
        return "observed-signature-required"
    return ""


def _merge_required_headers(headers: dict, required_headers: dict) -> dict:
    merged = dict(headers or {{}})
    for key, value in (required_headers or {{}}).items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


async def _resolve_required_headers(page) -> dict:
    if not REQUIRED_SPEC_HEADERS:
        return {{}}
    return await page.evaluate(
        """(required) => {{
            const results = {{}};
            const ua = navigator.userAgent || "";
            const lang = navigator.language || "";
            const size = `${{window.innerWidth || screen.width || 0}}x${{window.innerHeight || screen.height || 0}}`;
            for (const name of required) {{
                const lowered = String(name || "").toLowerCase();
                if (lowered.includes("fingerprint")) {{
                    results[name] = [ua, lang, size, location.href || ""].filter(Boolean).join("|");
                }} else if (lowered.includes("token") || lowered.includes("nonce") || lowered.includes("csrf")) {{
                    results[name] = "observed-runtime-required";
                }} else if (lowered.includes("signature")) {{
                    results[name] = "observed-signature-required";
                }}
            }}
            return results;
        }}""",
        REQUIRED_SPEC_HEADERS,
    )


async def _request_via_browser() -> dict:
    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context_kwargs = {{}}
            if BROWSER_USER_AGENT:
                context_kwargs["user_agent"] = BROWSER_USER_AGENT
            context = await browser.new_context(**context_kwargs)
            if OBSERVED_PLAYWRIGHT_COOKIES:
                await context.add_cookies(OBSERVED_PLAYWRIGHT_COOKIES)
            page = await context.new_page()
            await page.goto(TARGET_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
            runtime_required_headers = await _resolve_required_headers(page)
            browser_headers = _merge_required_headers(OBSERVED_BROWSER_HEADERS, runtime_required_headers)
            page_snapshot = await page.evaluate(
                """() => {{
                    const anchors = Array.from(document.querySelectorAll("a[href]"));
                    const seen = new Set();
                    const items = [];
                    for (const anchor of anchors) {{
                        const text = (anchor.textContent || "").replace(/\\\\s+/g, " ").trim();
                        const href = anchor.href || "";
                        if (!text || !href) continue;
                        if (text.length < 8) continue;
                        const key = `${{text}}@@${{href}}`;
                        if (seen.has(key)) continue;
                        seen.add(key);
                        items.push({{ text, href }});
                        if (items.length >= 20) break;
                    }}
                    return {{
                        title: document.title || "",
                        items,
                        itemCount: items.length,
                    }};
                }}""",
            )
            result = await page.evaluate(
                """async (payload) => {{
                    const response = await fetch(payload.url, {{
                        method: payload.method,
                        headers: payload.headers,
                        body: payload.body || undefined,
                        credentials: "include",
                    }});
                    const text = await response.text();
                    let data;
                    try {{
                        data = JSON.parse(text);
                    }} catch {{
                        data = {{ text: text.slice(0, 5000) }};
                    }}
                    return {{
                        status: response.status,
                        headers: Object.fromEntries(response.headers.entries()),
                        data,
                    }};
                }}""",
                {{
                    "url": OBSERVED_URL,
                    "method": OBSERVED_METHOD,
                    "headers": browser_headers,
                    "body": OBSERVED_BODY,
                }},
            )
            text_preview = ""
            data_payload = result.get("data")
            status_code = int(result.get("status") or 0)
            if isinstance(data_payload, dict):
                text_preview = str(data_payload.get("text") or "")
            if page_snapshot.get("itemCount", 0) >= 5 and (
                "captcha" in text_preview.lower()
                or "blocked" in text_preview.lower()
                or status_code in {403, 429}
            ):
                return {{
                    "status": 200,
                    "headers": {{}},
                    "data": {{
                        "mode": "browser_page_snapshot",
                        "title": page_snapshot.get("title", ""),
                        "items": page_snapshot.get("items", []),
                    }},
                }}
            if page_snapshot.get("itemCount", 0) >= 5 and not result.get("status"):
                return {{
                    "status": 200,
                    "headers": {{}},
                    "data": {{
                        "mode": "browser_page_snapshot",
                        "title": page_snapshot.get("title", ""),
                        "items": page_snapshot.get("items", []),
                    }},
                }}
            return result
    finally:
        if context is not None:
            await context.close()
        if browser is not None:
            await browser.close()


async def _request_via_httpx() -> dict:
    required_headers = {{name: _guess_required_header_value(name) for name in REQUIRED_SPEC_HEADERS}}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=OBSERVED_COOKIES) as client:
        response = await client.request(
            method=OBSERVED_METHOD,
            url=OBSERVED_URL,
            headers=_merge_required_headers(OBSERVED_HEADERS, required_headers),
            content=OBSERVED_BODY.encode("utf-8") if OBSERVED_BODY else None,
        )
        try:
            data = response.json()
        except Exception:
            data = {{"text": response.text[:5000]}}
        return {{
            "status": response.status_code,
            "headers": dict(response.headers),
            "data": data,
        }}


async def make_request() -> dict:
    browser_error = ""
    try:
        return await _request_via_browser()
    except Exception as exc:
        browser_error = str(exc)
    result = await _request_via_httpx()
    if browser_error:
        result["browser_error"] = browser_error
    return result


async def main():
    result = await make_request()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    asyncio.run(main())
'''

    @staticmethod
    def _required_header_names(signature_spec: SignatureSpec | None) -> list[str]:
        if signature_spec is None:
            return []
        required = list(signature_spec.header_policy.get("required", []) if signature_spec.header_policy else [])
        required.extend(signature_spec.fingerprint_fields.keys())
        required.extend(signature_spec.runtime_token_fields.keys())
        required.extend(key for key in signature_spec.signing_outputs.keys() if str(key).lower().startswith("x-"))
        return list(dict.fromkeys(str(item) for item in required if item))

    @staticmethod
    def _select_observed_request(
        target_requests: list[RequestCapture],
        signature_spec: SignatureSpec | None,
    ) -> RequestCapture:
        if not target_requests:
            raise ValueError("observed replay requires at least one captured request")
        preferred_url = ""
        preferred_method = ""
        if signature_spec:
            preferred_url = str(signature_spec.transport_profile.get("url_pattern") or "")
            preferred_method = str(signature_spec.transport_profile.get("method") or "").upper()
        if preferred_url:
            for request in target_requests:
                if request.url == preferred_url and (not preferred_method or request.method.upper() == preferred_method):
                    return request
        return target_requests[0]

    def _generate_python(
        self,
        url: str,
        algorithm: str,
        sig_type: str,
        key_location: str,
        hypothesis: str,
        api_endpoints: list[str] | None = None,
        extracted_key: dict[str, Any] | None = None,
        signature_spec: SignatureSpec | None = None,
    ) -> str:
        api_endpoints = list(api_endpoints or [])
        sign_field = self._derive_sign_field(signature_spec)
        timestamp_field = self._derive_timestamp_field(signature_spec)
        default_params = self._derive_default_params(signature_spec)
        algos = str(algorithm or "").lower()

        if "hmac" in algos or "sha" in algos:
            sig_impl = self._python_hmac_impl(algos, extracted_key)
        elif "aes" in algos:
            sig_impl = self._python_aes_impl(extracted_key)
        elif "rsa" in algos:
            sig_impl = self._python_rsa_impl()
        else:
            sig_impl = self._python_generic_impl(extracted_key)

        endpoints_info = ""
        if api_endpoints:
            endpoints_str = "\n".join(f"- {endpoint}" for endpoint in api_endpoints[:5])
            endpoints_info = f"\n## Detected API Endpoints\n{endpoints_str}"

        return f'''"""
Auto-generated crawler for {url}
Generated by Axelo unified engine

Signature Analysis:
- Algorithm: {algorithm}
- Type: {sig_type}
- Hypothesis: {hypothesis[:100]}{endpoints_info}
- Key location hint: {key_location or "unknown"}

Instructions:
1. Confirm SignatureSpec coverage before using this crawler in production.
2. Replace SECRET_KEY only when extraction did not recover a grounded key.
3. Adjust parameter construction only if verification flags missing signed fields.
"""

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime

import httpx

{sig_impl}


async def make_request(url: str, params: dict | None = None) -> dict:
    """Make authenticated request."""
    signature = generate_signature(SECRET_KEY, params or {{}})
    request_params = dict(params or {{}})
    request_params["{sign_field}"] = signature
    request_params["{timestamp_field}"] = str(int(datetime.now().timestamp() * 1000))

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={{
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }},
    ) as client:
        response = await client.get(url, params=request_params)
        return {{
            "status": response.status_code,
            "headers": dict(response.headers),
            "data": response.text,
            "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
        }}


async def main():
    target_url = "{url}"
    params = {default_params}
    result = await make_request(target_url, params)
    print(f"Status: {{result['status']}}")
    print(f"Response: {{result['data'][:500]}}")


if __name__ == "__main__":
    asyncio.run(main())
'''

    def _generate_page_extract_python(self, url: str) -> str:
        return f'''"""
Page extraction crawler for {url}
Generated by Axelo unified engine

Strategy:
- generation_mode: page_extract
- purpose: collect listing data directly from the rendered page when reverse evidence is too weak
"""

import asyncio
import json

from playwright.async_api import async_playwright


TARGET_URL = {json.dumps(url, ensure_ascii=False)}


async def extract_listing_items(page):
    return await page.evaluate(
        """() => {{
            const priceRegex = /(?:[$€£¥]|RM|Rp|IDR|CNY|RMB|NT\\$|₱)\\s*\\d[\\d.,]*/i;
            const nodes = Array.from(document.querySelectorAll("article, li, div, section, a[href]"));
            const results = [];
            const seen = new Set();
            for (const node of nodes) {{
                const anchor = node.matches("a[href]") ? node : node.querySelector("a[href]");
                if (!anchor) continue;
                const href = anchor.href || anchor.getAttribute("href") || "";
                const text = (anchor.textContent || node.textContent || "").replace(/\\s+/g, " ").trim();
                if (!href || !text || text.length < 8) continue;
                const key = `${{text}}@@${{href}}`;
                if (seen.has(key)) continue;
                seen.add(key);
                const blockText = (node.textContent || "").replace(/\\s+/g, " ").trim();
                const priceMatch = blockText.match(priceRegex);
                const image = (node.querySelector("img[src]") || anchor.querySelector("img[src]"))?.src || "";
                results.push({{
                    title: text,
                    url: href,
                    price: priceMatch ? priceMatch[0] : "",
                    image: image,
                }});
                if (results.length >= 25) break;
            }}
            return results;
        }}"""
    )


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)
        items = await extract_listing_items(page)
        payload = {{
            "status": 200,
            "items": items,
            "item_count": len(items),
        }}
        print(json.dumps(payload, ensure_ascii=False))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
'''

    @staticmethod
    def _derive_sign_field(signature_spec: SignatureSpec | None) -> str:
        if signature_spec:
            fields = list((signature_spec.signing_outputs or signature_spec.output_fields).keys())
            if fields:
                return fields[0]
        return "signature"

    @staticmethod
    def _derive_timestamp_field(signature_spec: SignatureSpec | None) -> str:
        if signature_spec:
            for field_name in signature_spec.signing_inputs or signature_spec.input_fields:
                lowered = field_name.lower()
                if "timestamp" in lowered or lowered in {"ts", "t"}:
                    return field_name
        return "timestamp"

    @staticmethod
    def _derive_default_params(signature_spec: SignatureSpec | None) -> str:
        params: dict[str, Any] = {}
        if signature_spec:
            for field_name in signature_spec.signing_inputs or signature_spec.input_fields:
                lowered = field_name.lower()
                if field_name in params or "signature" in lowered:
                    continue
                if "page" in lowered:
                    params[field_name] = 1
                elif "size" in lowered or "limit" in lowered:
                    params[field_name] = 20
                elif "keyword" in lowered or "query" in lowered or lowered == "q":
                    params[field_name] = "example"
                elif "timestamp" in lowered or lowered in {"ts", "t"}:
                    continue
        if not params:
            params = {"page": 1, "size": 20}
        items = ",\n        ".join(f'"{key}": {value!r}' for key, value in params.items())
        return "{\n        " + items + "\n    }"

    def _python_hmac_impl(self, algo: str, extracted_key: dict[str, Any] | None = None) -> str:
        hash_algo = "sha256"
        if "sha1" in algo:
            hash_algo = "sha1"
        elif "sha512" in algo:
            hash_algo = "sha512"
        elif "md5" in algo:
            hash_algo = "md5"

        key_value = "YOUR_SECRET_KEY_HERE"
        key_source_info = "# REPLACE WITH ACTUAL KEY"
        if extracted_key and extracted_key.get("key_value"):
            key_value = extracted_key["key_value"]
            key_source_info = f"# Key extracted from JS ({extracted_key.get('key_source', 'unknown')})"

        return f'''
# Configuration {key_source_info}
SECRET_KEY = "{key_value}"

def generate_signature(secret_key: str, params: dict) -> str:
    sorted_params = sorted(params.items())
    param_str = "&".join([f"{{k}}={{v}}" for k, v in sorted_params])
    message = f"{{param_str}}&key={{secret_key}}"
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.{hash_algo}).hexdigest()
    return signature
'''

    def _python_aes_impl(self, extracted_key: dict[str, Any] | None = None) -> str:
        key_value = "YOUR_32BYTE_KEY_HERE"
        key_source_info = "# Must be 32 bytes for AES-256"
        if extracted_key and extracted_key.get("key_value"):
            key_value = extracted_key["key_value"]
            key_source_info = f"# Key extracted from JS ({extracted_key.get('key_source', 'unknown')})"
        return f'''
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

SECRET_KEY = "{key_value}"  # {key_source_info}

def generate_signature(secret_key: str, params: dict) -> str:
    data = json.dumps(params, sort_keys=True)
    padded = pad(data.encode(), AES.block_size)
    cipher = AES.new(secret_key.encode(), AES.MODE_CBC, iv=b"0000000000000000")
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode()
'''

    @staticmethod
    def _python_rsa_impl() -> str:
        return '''
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
YOUR_PRIVATE_KEY_HERE
-----END RSA PRIVATE KEY-----"""
SECRET_KEY = PRIVATE_KEY

def generate_signature(secret_key: str, params: dict) -> str:
    sorted_params = sorted(params.items())
    message = "&".join([f"{k}={v}" for k, v in sorted_params])
    key = RSA.import_key(secret_key)
    digest = SHA256.new(message.encode())
    signature = pkcs1_15.new(key).sign(digest)
    return base64.b64encode(signature).decode()
'''

    @staticmethod
    def _python_generic_impl(extracted_key: dict[str, Any] | None = None) -> str:
        key_value = "YOUR_SECRET_KEY_HERE"
        key_source_info = "# REPLACE WITH ACTUAL KEY"
        if extracted_key and extracted_key.get("key_value"):
            key_value = extracted_key["key_value"]
            key_source_info = f"# Key extracted from JS ({extracted_key.get('key_source', 'unknown')})"
        return f'''
# Generic signature placeholder {key_source_info}
SECRET_KEY = "{key_value}"

def generate_signature(secret_key: str, params: dict) -> str:
    sorted_params = sorted(params.items())
    param_str = "&".join([f"{{k}}={{v}}" for k, v in sorted_params])
    message = f"{{param_str}}&key={{secret_key}}"
    return hashlib.sha256(message.encode()).hexdigest()
'''

    def _generate_js(
        self,
        url: str,
        algorithm: str,
        sig_type: str,
        key_location: str,
        signature_spec: SignatureSpec | None = None,
    ) -> str:
        algos = str(algorithm or "").lower()
        sign_field = self._derive_sign_field(signature_spec)
        timestamp_field = self._derive_timestamp_field(signature_spec)

        if "hmac" in algos or "sha" in algos:
            sig_impl = self._js_hmac_impl(algos)
        elif "aes" in algos:
            sig_impl = self._js_aes_impl()
        else:
            sig_impl = self._js_generic_impl()

        return f'''/**
 * Auto-generated crawler for {url}
 * Algorithm: {algorithm}
 * Type: {sig_type}
 * Key location hint: {key_location or "unknown"}
 */

{sig_impl}

async function makeRequest(url, params = {{}}) {{
    const signature = await generateSignature(SECRET_KEY, params);
    const requestParams = new URLSearchParams(params);
    requestParams.append("{sign_field}", signature);
    requestParams.append("{timestamp_field}", Date.now().toString());

    const fullUrl = `${{url}}?${{requestParams.toString()}}`;
    const response = await fetch(fullUrl, {{
        method: "GET",
        headers: {{
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        }},
    }});

    return {{
        status: response.status,
        data: await response.text(),
        json: await response.json().catch(() => null),
    }};
}}

(async () => {{
    const result = await makeRequest("{url}", {{ page: 1, size: 20 }});
    console.log(`Status: ${{result.status}}`);
    console.log(`Response: ${{result.data.substring(0, 500)}}`);
}})();
'''

    @staticmethod
    def _js_hmac_impl(algo: str) -> str:
        hash_algo = "SHA-256"
        if "sha1" in algo:
            hash_algo = "SHA-1"
        elif "sha512" in algo:
            hash_algo = "SHA-512"
        return f'''
const SECRET_KEY = "YOUR_SECRET_KEY_HERE";

async function generateSignature(secretKey, params) {{
    const sorted = Object.keys(params).sort();
    const paramStr = sorted.map((key) => `${{key}}=${{params[key]}}`).join("&");
    const message = `${{paramStr}}&key=${{secretKey}}`;
    const encoder = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
        "raw",
        encoder.encode(secretKey),
        {{ name: "HMAC", hash: "{hash_algo}" }},
        false,
        ["sign"],
    );
    const signature = await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(message));
    return Array.from(new Uint8Array(signature)).map((item) => item.toString(16).padStart(2, "0")).join("");
}}
'''

    @staticmethod
    def _js_aes_impl() -> str:
        return '''
const SECRET_KEY = "YOUR_32BYTE_KEY_HERE";

async function generateSignature(secretKey, params) {
    const key = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(secretKey),
        { name: "AES-CBC" },
        false,
        ["encrypt"],
    );
    const data = JSON.stringify(params, Object.keys(params).sort());
    const iv = new Uint8Array(16);
    const encrypted = await crypto.subtle.encrypt({ name: "AES-CBC", iv }, key, new TextEncoder().encode(data));
    return btoa(String.fromCharCode(...new Uint8Array(encrypted)));
}
'''

    @staticmethod
    def _js_generic_impl() -> str:
        return '''
const SECRET_KEY = "YOUR_SECRET_KEY_HERE";

async function generateSignature(secretKey, params) {
    const sorted = Object.keys(params).sort();
    const paramStr = sorted.map((key) => `${key}=${params[key]}`).join("&");
    const message = `${paramStr}&key=${secretKey}`;
    const data = new TextEncoder().encode(message);
    const digest = await crypto.subtle.digest("SHA-256", data);
    return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, "0")).join("");
}
'''


get_registry().register(CodegenTool())
