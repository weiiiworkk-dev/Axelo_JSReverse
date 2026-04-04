from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from axelo.models.contracts import CapabilityProfile, DatasetContract, RequestContract
from axelo.models.target import RequestCapture, TargetSite


_HEADER_PRIORITY = (
    "authorization",
    "x-requested-with",
    "x-csrf-token",
    "x-csrftoken",
    "x-sign",
    "sign",
    "signature",
    "sz-token",
    "af-ac-enc-dat",
    "af-ac-enc-id",
    "x-sap-ri",
)


def build_request_contract(capture: RequestCapture, target: TargetSite) -> RequestContract:
    parsed = urlsplit(capture.url)
    url_pattern = f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"
    query_fields = [key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    body_fields = _body_fields(capture.request_body)
    required_headers: list[str] = []
    optional_headers: list[str] = []
    anti_bot_signals: list[str] = []
    for key in (capture.request_headers or {}).keys():
        lowered = str(key).lower()
        if lowered in {"cookie", "host", "content-length", "connection"} or lowered.startswith("sec-"):
            continue
        if any(signal in lowered for signal in ("sign", "token", "nonce", "sap", "csrf", "af-ac-enc", "authorization")):
            if key not in required_headers:
                required_headers.append(key)
        else:
            optional_headers.append(key)
        if any(signal in lowered for signal in ("captcha", "csrf", "sign", "token", "nonce", "sap", "af-ac-enc")):
            anti_bot_signals.append(key)

    response_shape = _response_shape(capture)
    cookie_requirements = _cookie_requirements(target)
    auth_mode = _auth_mode(capture, target, cookie_requirements)
    required_headers = _sort_headers(required_headers)
    optional_headers = _sort_headers(optional_headers)

    return RequestContract(
        method=(capture.method or "GET").upper(),
        url_pattern=url_pattern,
        query_fields=query_fields,
        body_fields=body_fields,
        required_headers=required_headers,
        optional_headers=optional_headers,
        cookie_requirements=cookie_requirements,
        response_shape=response_shape,
        anti_bot_signals=anti_bot_signals,
        auth_mode=auth_mode,
    )


def build_dataset_contract(target: TargetSite, contract: RequestContract | None = None) -> DatasetContract:
    intent = target.intent
    dataset_name = intent.dataset_name or target.dataset_contract.dataset_name or "default"
    record_path = target.dataset_contract.record_path if target.dataset_contract.record_path else _default_record_path(intent.resource_kind)
    field_map = dict(target.dataset_contract.field_map)
    if not field_map:
        field_map = _default_field_map(intent.resource_kind)
    primary_keys = list(target.dataset_contract.primary_keys or _default_primary_keys(intent.resource_kind))
    normalizers = list(target.dataset_contract.normalizers or _default_normalizers(intent.resource_kind, contract))
    return DatasetContract(
        dataset_name=dataset_name,
        schema_version=target.dataset_contract.schema_version or "v1",
        primary_keys=primary_keys,
        record_path=record_path,
        field_map=field_map,
        normalizers=normalizers,
    )


def derive_capability_profile(
    target: TargetSite,
    *,
    contract: RequestContract | None = None,
    codegen_strategy: str | None = None,
) -> CapabilityProfile:
    contract = contract or target.selected_contract
    anti_bot_signals = set((contract.anti_bot_signals if contract else []) or [])
    codegen_strategy = codegen_strategy or "python_reconstruct"
    needs_storage_state = bool(target.session_state.storage_state_path or target.requires_login or (contract and contract.cookie_requirements))
    needs_fingerprint = any("fingerprint" in signal.lower() or "sap" in signal.lower() for signal in anti_bot_signals)
    needs_bridge = codegen_strategy == "js_bridge" or needs_fingerprint
    needs_browser = needs_bridge or needs_storage_state
    supports_pure_http = not needs_bridge
    supports_parallel_fetch = supports_pure_http and not needs_storage_state and (target.crawl_item_limit >= 100)
    supports_pagination = target.crawl_page_limit is None or target.crawl_page_limit != 1
    return CapabilityProfile(
        needs_browser=needs_browser,
        needs_storage_state=needs_storage_state,
        needs_bridge=needs_bridge,
        needs_fingerprint=needs_fingerprint,
        supports_pure_http=supports_pure_http,
        supports_pagination=supports_pagination,
        supports_parallel_fetch=supports_parallel_fetch,
    )


def request_contract_summary(contract: RequestContract) -> list[str]:
    return [
        f"method={contract.method}",
        f"url={contract.url_pattern}",
        f"query={','.join(contract.query_fields) or '-'}",
        f"body={','.join(contract.body_fields) or '-'}",
        f"auth={contract.auth_mode}",
    ]


def _body_fields(body: bytes | None) -> list[str]:
    if not body:
        return []
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="ignore")
    text = text.strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return [str(key) for key in payload.keys()]
    except Exception:
        pass
    return [key for key, _ in parse_qsl(text, keep_blank_values=True)]


def _response_shape(capture: RequestCapture) -> dict[str, Any]:
    content_type = (capture.response_headers or {}).get("content-type") or (capture.response_headers or {}).get("Content-Type") or ""
    shape: dict[str, Any] = {"content_type": content_type}
    body = capture.response_body or b""
    if not body:
        return shape
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="ignore")
    text = text.strip()
    if not text:
        return shape
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            shape["root"] = "object"
            shape["top_level_keys"] = [str(key) for key in list(payload.keys())[:12]]
        elif isinstance(payload, list):
            shape["root"] = "array"
            shape["length_hint"] = len(payload)
    except Exception:
        shape["root"] = "text"
    return shape


def _cookie_requirements(target: TargetSite) -> list[str]:
    cookie_names: list[str] = []
    for cookie in target.session_state.cookies:
        name = cookie.get("name")
        if name:
            cookie_names.append(str(name))
    return cookie_names[:20]


def _auth_mode(capture: RequestCapture, target: TargetSite, cookie_requirements: list[str]) -> str:
    headers = {str(key).lower() for key in (capture.request_headers or {}).keys()}
    if "authorization" in headers:
        return "authorization_header"
    if cookie_requirements:
        return "cookie_session"
    if target.requires_login is False:
        return "anonymous"
    return "unknown"


def _sort_headers(headers: list[str]) -> list[str]:
    return sorted(
        dict.fromkeys(headers),
        key=lambda item: (
            0 if item.lower() in _HEADER_PRIORITY else 1,
            _HEADER_PRIORITY.index(item.lower()) if item.lower() in _HEADER_PRIORITY else 999,
            item.lower(),
        ),
    )


def _default_record_path(resource_kind: str) -> str:
    if resource_kind in {"search_results", "product_listing", "content_listing"}:
        return "$.items[*]"
    if resource_kind == "reviews":
        return "$.reviews[*]"
    return "$"


def _default_field_map(resource_kind: str) -> dict[str, str]:
    if resource_kind in {"search_results", "product_listing"}:
        return {
            "id": "itemid",
            "title": "name",
            "price": "price",
            "url": "item_url",
        }
    if resource_kind == "reviews":
        return {"id": "review_id", "content": "content", "rating": "rating"}
    return {}


def _default_primary_keys(resource_kind: str) -> list[str]:
    if resource_kind in {"search_results", "product_listing", "content_listing"}:
        return ["id"]
    if resource_kind == "reviews":
        return ["id"]
    return []


def _default_normalizers(resource_kind: str, contract: RequestContract | None) -> list[str]:
    normalizers = ["drop_null_fields"]
    if resource_kind in {"search_results", "product_listing"}:
        normalizers.append("normalize_price_to_string")
    if contract and contract.response_shape.get("root") == "text":
        normalizers.append("parse_json_if_possible")
    return normalizers

