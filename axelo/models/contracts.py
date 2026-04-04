from __future__ import annotations

from datetime import datetime
import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field, model_validator


def infer_resource_kind_from_goal(goal: str) -> str:
    lowered = (goal or "").strip().lower()
    if any(token in lowered for token in ("search", "搜索", "query", "keyword")):
        return "search_results"
    if any(token in lowered for token in ("price", "价格", "product", "商品", "sku", "item")):
        return "product_listing"
    if any(token in lowered for token in ("review", "评论", "comment")):
        return "reviews"
    if any(token in lowered for token in ("video", "内容", "content", "feed", "list")):
        return "content_listing"
    if any(token in lowered for token in ("user", "账号", "account", "profile")):
        return "user_profile"
    return "generic_resource"


def infer_dataset_name(resource_kind: str, selector_hint: str = "") -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", (resource_kind or "default").strip().lower()).strip("_")
    if not base:
        base = "default"
    if selector_hint:
        normalized_hint = re.sub(r"[^a-zA-Z0-9_]+", "_", selector_hint.strip().lower()).strip("_")
        if normalized_hint:
            return f"{base}_{normalized_hint[:32]}"
    return base


def build_intent_fingerprint(
    *,
    resource_kind: str,
    selector_hint: str,
    known_endpoint: str,
    item_limit: int,
    page_limit: int | None,
    output_format: str,
    dataset_name: str,
) -> str:
    payload = "|".join(
        [
            resource_kind.strip().lower(),
            selector_hint.strip().lower(),
            known_endpoint.strip().lower(),
            str(item_limit),
            str(page_limit or 0),
            output_format.strip().lower(),
            dataset_name.strip().lower(),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class CaptureIntent(BaseModel):
    resource_kind: str = "generic_resource"
    selector_hint: str = ""
    known_endpoint: str = ""
    item_limit: int = Field(default=100, ge=1)
    page_limit: int | None = Field(default=None, ge=1)
    output_format: str = "print"
    dataset_name: str = ""

    @model_validator(mode="after")
    def _fill_dataset_name(self) -> "CaptureIntent":
        if not self.dataset_name:
            self.dataset_name = infer_dataset_name(self.resource_kind, self.selector_hint)
        return self

    @property
    def fingerprint(self) -> str:
        return build_intent_fingerprint(
            resource_kind=self.resource_kind,
            selector_hint=self.selector_hint,
            known_endpoint=self.known_endpoint,
            item_limit=self.item_limit,
            page_limit=self.page_limit,
            output_format=self.output_format,
            dataset_name=self.dataset_name,
        )

    @classmethod
    def from_legacy(
        cls,
        *,
        goal: str,
        target_hint: str = "",
        known_endpoint: str = "",
        item_limit: int = 100,
        page_limit: int | None = None,
        output_format: str = "print",
        dataset_name: str = "",
    ) -> "CaptureIntent":
        return cls(
            resource_kind=infer_resource_kind_from_goal(goal),
            selector_hint=target_hint,
            known_endpoint=known_endpoint,
            item_limit=item_limit,
            page_limit=page_limit,
            output_format=output_format,
            dataset_name=dataset_name,
        )


class RequestContract(BaseModel):
    method: str = "GET"
    url_pattern: str = ""
    query_fields: list[str] = Field(default_factory=list)
    body_fields: list[str] = Field(default_factory=list)
    required_headers: list[str] = Field(default_factory=list)
    optional_headers: list[str] = Field(default_factory=list)
    cookie_requirements: list[str] = Field(default_factory=list)
    response_shape: dict[str, Any] = Field(default_factory=dict)
    anti_bot_signals: list[str] = Field(default_factory=list)
    auth_mode: str = "unknown"

    @property
    def contract_hash(self) -> str:
        payload = "|".join(
            [
                self.method.upper(),
                self.url_pattern,
                ",".join(sorted(self.query_fields)),
                ",".join(sorted(self.body_fields)),
                ",".join(sorted(self.required_headers)),
                ",".join(sorted(self.cookie_requirements)),
                ",".join(sorted(self.anti_bot_signals)),
                self.auth_mode,
            ]
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


class DatasetContract(BaseModel):
    dataset_name: str = "default"
    schema_version: str = "v1"
    primary_keys: list[str] = Field(default_factory=list)
    record_path: str = ""
    field_map: dict[str, str] = Field(default_factory=dict)
    normalizers: list[str] = Field(default_factory=list)


class CapabilityProfile(BaseModel):
    needs_browser: bool = False
    needs_storage_state: bool = False
    needs_bridge: bool = False
    needs_fingerprint: bool = False
    supports_pure_http: bool = True
    supports_pagination: bool = True
    supports_parallel_fetch: bool = False


class VerificationProfile(BaseModel):
    live_verify: bool = False
    stability_runs: int = 1
    failure_modes: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    family_id: str = "unknown"
    request_contract_hash: str = ""
    evidence_summary: list[str] = Field(default_factory=list)
    observed_headers: list[str] = Field(default_factory=list)
    observed_endpoints: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class FailureCase(BaseModel):
    classification: str
    request_contract_hash: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    repair_strategy: str = ""
    templated: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class AdapterPackage(BaseModel):
    package_version: str = "v1"
    site_key: str
    intent_fingerprint: str = ""
    family_id: str = "unknown"
    request_contract_hash: str = ""
    manifest: dict[str, Any] = Field(default_factory=dict)
    request_contract: RequestContract = Field(default_factory=RequestContract)
    signature_spec: dict[str, Any] = Field(default_factory=dict)
    capability_profile: CapabilityProfile = Field(default_factory=CapabilityProfile)
    dataset_contract: DatasetContract = Field(default_factory=DatasetContract)
    crawler_artifact: str = ""
    bridge_artifact: str = ""
    verification_profile: VerificationProfile = Field(default_factory=VerificationProfile)
    compatibility_tags: list[str] = Field(default_factory=list)
    source_session_id: str = ""
    manifest_ref: str = ""
    adapter_package_ref: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

