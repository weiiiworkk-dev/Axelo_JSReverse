"""
Unified engine executor for tool dispatch and context propagation.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

from axelo.config import settings
from axelo.models.signature import SignatureSpec
from axelo.tools.base import ToolResult, ToolState, ToolStatus, get_registry

log = structlog.get_logger()
DEBUG_LOG_PATH = settings.workspace / "debug.log"


@dataclass
class ExecutionContext:
    initial_input: dict[str, Any] = field(default_factory=dict)
    current_tool: str = ""
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    session_id: str = ""

    def add_result(self, tool_name: str, result: ToolResult) -> None:
        self.tool_results[tool_name] = result
        self.history.append(tool_name)

    def get_result(self, tool_name: str) -> ToolResult | None:
        return self.tool_results.get(tool_name)

    def get_all_outputs(self) -> dict[str, dict[str, Any]]:
        return {
            name: result.output
            for name, result in self.tool_results.items()
            if result.success
        }


class ToolExecutor:
    def __init__(self, registry=None):
        self.registry = registry or get_registry()
        self.state = ToolState()
        self.state.enable_context_diff(True)
        self.ctx = ExecutionContext()

    @staticmethod
    def _collect_js_code(merged: dict[str, Any], *, bundle_limit: int = 5, bundle_bytes: int = 50000, fallback_bytes: int = 100000) -> str:
        bundles = merged.get("bundles") or []
        if isinstance(bundles, list) and bundles:
            js_contents: list[str] = []
            for bundle in bundles[:bundle_limit]:
                if not isinstance(bundle, dict):
                    continue
                content = str(bundle.get("content") or "")
                if content:
                    js_contents.append(content[:bundle_bytes])
            if js_contents:
                return "\n\n".join(js_contents)

        for key in ("deobfuscated_code", "html_content", "content"):
            content = str(merged.get(key) or "")
            if content:
                return content[:fallback_bytes]
        return ""

    @staticmethod
    def _read_text(path_value: Any) -> str:
        if not path_value:
            return ""
        try:
            path = Path(path_value)
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            return ""
        return ""

    @staticmethod
    def _repair_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return text
        suspicious = ("Ã", "Â", "æ", "ç", "ä", "è", "é", "ï", "œ")
        if any(marker in text for marker in suspicious):
            for codec in ("latin1", "cp1252"):
                try:
                    repaired = text.encode(codec).decode("utf-8")
                    if repaired.strip():
                        return repaired.strip()
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
        return text

    @classmethod
    def _looks_unknown(cls, value: Any) -> bool:
        text = cls._repair_text(value)
        if not text:
            return True
        stripped = text.replace("?", "").replace("？", "").strip()
        if not stripped:
            return True
        lowered = text.lower()
        unknown_markers = {
            "unknown",
            "none",
            "null",
            "n/a",
            "missing",
            "not detected",
            "not_found",
            "undetected",
            "undefined",
        }
        if lowered in unknown_markers:
            return True
        fuzzy_markers = ("未知", "未检测", "未发现", "未识别", "无可用", "empty", "not available")
        return any(marker in text for marker in fuzzy_markers)

    @classmethod
    def _normalize_algorithm_id(cls, value: Any) -> str:
        text = cls._repair_text(value)
        if cls._looks_unknown(text):
            return "unknown"
        lowered = text.lower()
        patterns = (
            (r"hmac(?:[-_\s]?sha(?:[-_\s]?256)?)", "hmac_sha256"),
            (r"sha(?:[-_\s]?512)\b", "sha512"),
            (r"sha(?:[-_\s]?256)\b", "sha256"),
            (r"sha(?:[-_\s]?1)\b", "sha1"),
            (r"\bmd5\b", "md5"),
            (r"aes(?:[-_/]?gcm)\b", "aes_gcm"),
            (r"aes(?:[-_/]?cbc)\b", "aes_cbc"),
            (r"\baes\b", "aes"),
            (r"\brsa\b", "rsa"),
            (r"\becdsa\b", "ecdsa"),
            (r"\bbase64\b", "base64"),
            (r"fingerprint", "fingerprint"),
        )
        for pattern, normalized in patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return normalized
        if "自定义" in text or "custom" in lowered or "signkey" in lowered:
            return "custom"
        return "unknown"

    @classmethod
    def _normalize_family_id(cls, value: Any, algorithm_id: str) -> str:
        text = cls._repair_text(value)
        if cls._looks_unknown(text):
            return algorithm_id if algorithm_id != "unknown" else "unknown"
        lowered = text.lower()
        if "自定义" in text or "custom" in lowered:
            return "custom"
        normalized = cls._normalize_algorithm_id(text)
        return normalized if normalized != "unknown" else (algorithm_id if algorithm_id != "unknown" else "unknown")

    @classmethod
    def _normalize_key_source(cls, value: Any) -> str:
        text = cls._repair_text(value)
        if cls._looks_unknown(text):
            return "unknown"
        lowered = text.lower()
        markers = (
            ("hardcoded", ("硬编码", "hardcoded", "javascript", "js code", "bundle", "const", "constant", "signkey")),
            ("local_storage", ("localstorage", "local storage")),
            ("session_storage", ("sessionstorage", "session storage")),
            ("cookie", ("cookie", "document.cookie")),
            ("meta_tag", ("meta", "meta tag")),
            ("runtime", ("runtime", "memory", "window.")),
            ("api_response", ("response", "接口返回", "api response")),
        )
        for normalized, terms in markers:
            if any(term in lowered or term in text for term in terms):
                return normalized
        return lowered.replace(" ", "_")

    @classmethod
    def _normalize_bridge_target(cls, value: Any) -> str | None:
        text = cls._repair_text(value)
        if cls._looks_unknown(text):
            return None
        lowered = text.lower()
        if any(term in lowered for term in ("hardcoded", "javascript", "js code", "bundle", "const", "constant", "硬编码")):
            return None
        patterns = (
            r"(window\.[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)+)",
            r"(localStorage\.[A-Za-z_][\w$]*)",
            r"(sessionStorage\.[A-Za-z_][\w$]*)",
            r"(document\.cookie)",
            r"(px\.[A-Za-z_][\w$]*)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        dotted = re.search(r"([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*){1,3})", text)
        if dotted:
            return dotted.group(1)
        return None

    @classmethod
    def _extract_secret_candidate(cls, *values: Any) -> str:
        patterns = (
            r'(?i)(?:signkey|secretkey|secret|apikey|appkey|privatekey|token|key)\s*[:=]\s*["\']([A-Za-z0-9#@%&*_\-+/=]{8,128})["\']',
            r'(?i)["\'](?:signKey|secretKey|apiKey|appKey|token|key)["\']\s*:\s*["\']([A-Za-z0-9#@%&*_\-+/=]{8,128})["\']',
        )
        for value in values:
            text = cls._repair_text(value)
            if not text:
                continue
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        return ""

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in values if item))

    @classmethod
    def _normalize_param_format(cls, value: Any, request_fields: list[str]) -> str:
        text = cls._repair_text(value).lower()
        if "header" in text:
            return "header"
        if "query" in text:
            return "query_string"
        if "body" in text or "json" in text or "payload" in text:
            return "json_body"
        lowered_fields = [field.lower() for field in request_fields]
        header_like = any(field.startswith("x-") or "token" in field or "fingerprint" in field or "auth" in field for field in lowered_fields)
        query_like = any(field in {"signature", "sign", "sig", "nonce", "timestamp", "ts"} for field in lowered_fields)
        if header_like and query_like:
            return "mixed"
        if header_like:
            return "header"
        if query_like:
            return "query_string"
        return ""

    @classmethod
    def _is_probable_signature_field(cls, field_name: str) -> bool:
        lowered = field_name.lower()
        if not lowered:
            return False
        if field_name.upper() == field_name and "_" in field_name:
            return False
        if field_name[:1].isupper():
            return False
        if any(noise in lowered for noise in ("modal", "iframe", "body", "open", "error", "failed", "empty", "illegal", "expired")):
            return False
        return any(term in lowered for term in ("sign", "signature", "auth"))

    @classmethod
    def _is_probable_fingerprint_field(cls, field_name: str) -> bool:
        lowered = field_name.lower()
        return any(term in lowered for term in ("fingerprint", "device_", "canvas", "webgl", "sensor"))

    @classmethod
    def _is_probable_runtime_token_field(cls, field_name: str) -> bool:
        lowered = field_name.lower()
        return any(term in lowered for term in ("token", "nonce", "timestamp", "csrf", "auth")) and not cls._is_probable_fingerprint_field(field_name)

    @classmethod
    def _derive_output_layers(cls, request_fields: list[str], param_format: str) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        signature_fields = {
            field: f"signature field inferred from {param_format or 'static evidence'}"
            for field in request_fields
            if cls._is_probable_signature_field(field)
        }
        fingerprint_fields = {
            field: f"fingerprint field inferred from {param_format or 'runtime evidence'}"
            for field in request_fields
            if cls._is_probable_fingerprint_field(field)
        }
        runtime_token_fields = {
            field: f"runtime token inferred from {param_format or 'observed request'}"
            for field in request_fields
            if cls._is_probable_runtime_token_field(field) and field not in signature_fields and field not in fingerprint_fields
        }
        if signature_fields or fingerprint_fields or runtime_token_fields:
            return signature_fields, fingerprint_fields, runtime_token_fields
        if param_format:
            field_name = "signature"
            if "header" in param_format:
                field_name = "x-signature"
            return ({field_name: f"signature field inferred from {param_format}"}, {}, {})
        return ({}, {}, {})

    @classmethod
    def _derive_header_policy(cls, request_fields: list[str], signature_fields: dict[str, str], fingerprint_fields: dict[str, str], runtime_token_fields: dict[str, str]) -> dict[str, list[str]]:
        required = [
            field for field in request_fields
            if cls._is_probable_signature_field(field) or cls._is_probable_runtime_token_field(field) or cls._is_probable_fingerprint_field(field)
        ]
        required.extend(
            field for field in {**signature_fields, **fingerprint_fields, **runtime_token_fields}
            if field.lower().startswith("x-")
        )
        return {
            "required": cls._dedupe_strings(required),
            "optional": [],
        }

    @staticmethod
    def _iter_observed_requests(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict) and item.get("url"):
                normalized.append(item)
        return normalized

    @classmethod
    def _extract_request_fields_from_observed_request(cls, request: dict[str, Any] | None) -> list[str]:
        if not isinstance(request, dict):
            return []
        fields: list[str] = []
        ignored = {
            "accept",
            "accept-language",
            "origin",
            "referer",
            "user-agent",
            "content-type",
            "content-length",
            "host",
            "connection",
        }
        headers = request.get("request_headers") or {}
        if isinstance(headers, dict):
            for key in headers:
                lowered = str(key).lower()
                if lowered.startswith("sec-") or lowered in ignored:
                    continue
                if lowered.startswith("x-") or any(term in lowered for term in ("sign", "signature", "token", "nonce", "fingerprint", "auth", "csrf")):
                    fields.append(str(key))
        return cls._dedupe_strings([cls._repair_text(item) for item in fields if item])

    @staticmethod
    def _primary_observed_request(requests: list[dict[str, Any]]) -> dict[str, Any] | None:
        return requests[0] if requests else None

    @staticmethod
    def _looks_runtime_bound_value(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if "defaulttoken" in lowered or "@@" in text:
            return True
        if len(text) >= 24 and any(ch.isdigit() for ch in text) and any(ch.isalpha() for ch in text):
            return True
        return False

    @staticmethod
    def _same_site(request_url: str, page_url: str) -> bool:
        request_host = urlparse(request_url).hostname or ""
        page_host = urlparse(page_url).hostname or ""
        if not request_host or not page_host:
            return False
        if request_host == page_host:
            return True
        page_suffix = page_host[4:] if page_host.startswith("www.") else page_host
        return bool(page_suffix and request_host.endswith(page_suffix))

    @classmethod
    def _observed_request_prefers_replay(
        cls,
        request: dict[str, Any] | None,
        *,
        page_url: str,
        output_fields: dict[str, str],
        secret_candidate: str,
        algorithm_id: str,
    ) -> bool:
        if not isinstance(request, dict):
            return False
        method = str(request.get("method") or "GET").upper()
        url = str(request.get("url") or "")
        headers = request.get("request_headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        lowered_headers = {str(key).lower(): str(value or "") for key, value in headers.items()}
        runtime_fields = [
            key for key in lowered_headers
            if any(term in key for term in ("token", "csrf", "fingerprint", "auth", "nonce", "sign", "signature"))
        ]
        runtime_values = [value for value in lowered_headers.values() if cls._looks_runtime_bound_value(value)]
        output_names = {field.lower() for field in output_fields}
        overlap_fields = [field for field in runtime_fields if field in output_names]
        same_site = False
        try:
            same_site = cls._same_site(url, page_url)
        except Exception:
            same_site = False

        if overlap_fields:
            return True
        if runtime_fields and (runtime_values or same_site):
            return True
        if method == "GET" and same_site and not secret_candidate and algorithm_id in {"unknown", "custom", "fingerprint", "base64"}:
            return True
        return False

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

    def _build_signature_spec(self, merged: dict[str, Any]) -> SignatureSpec | None:
        for key in ("signature_spec_model", "signature_spec"):
            spec = self._coerce_signature_spec(merged.get(key))
            if spec is not None:
                return spec

        analysis_model = merged.get("analysis_model")
        if analysis_model is not None:
            spec = self._coerce_signature_spec(getattr(analysis_model, "signature_spec", None))
            if spec is not None:
                return spec

        hypothesis_model = merged.get("hypothesis_model")
        if hypothesis_model is not None:
            spec = self._coerce_signature_spec(getattr(hypothesis_model, "signature_spec", None))
            if spec is not None:
                return spec

        sig_output = merged.get("signature_extractor") or merged.get("signature_extraction") or {}
        if not sig_output and any(merged.get(key) for key in ("key_value", "key_source", "algorithm", "param_format")):
            sig_output = {
                "key_value": merged.get("key_value"),
                "key_source": merged.get("key_source"),
                "algorithm": merged.get("algorithm"),
                "confidence": merged.get("confidence"),
                "param_format": merged.get("param_format"),
            }

        request_fields = merged.get("request_fields") or []
        if not isinstance(request_fields, list):
            request_fields = []
        request_fields.extend(merged.get("required_headers") or [])
        request_fields.extend(merged.get("required_query_fields") or [])
        request_fields.extend(merged.get("required_body_fields") or [])
        transport_profile = merged.get("transport_profile") or {}
        if isinstance(transport_profile, dict):
            request_fields.extend(transport_profile.get("request_fields") or [])
            request_fields.extend(transport_profile.get("query_fields") or [])
            request_fields.extend(transport_profile.get("body_fields") or [])
        request_fields = self._dedupe_strings([self._repair_text(item) for item in request_fields if item])
        observed_requests = self._iter_observed_requests(merged.get("target_requests") or merged.get("captured_requests") or [])
        primary_observed_request = self._primary_observed_request(observed_requests)
        request_fields.extend(self._extract_request_fields_from_observed_request(primary_observed_request))
        request_fields = self._dedupe_strings(request_fields)

        algorithm_candidates = merged.get("algorithms") or []
        if not isinstance(algorithm_candidates, list):
            algorithm_candidates = []
        algorithm_candidates = self._dedupe_strings(
            [self._repair_text(item) for item in algorithm_candidates if item]
        )

        raw_algorithm = sig_output.get("algorithm") or merged.get("algorithm") or ""
        if self._looks_unknown(raw_algorithm) and algorithm_candidates:
            raw_algorithm = algorithm_candidates[0]
        raw_family = merged.get("signature_type") or raw_algorithm or ""
        confidence = float(sig_output.get("confidence") or merged.get("confidence") or 0.0)
        raw_param_format = sig_output.get("param_format") or merged.get("param_format") or ""
        raw_key_source = sig_output.get("key_source") or merged.get("key_source") or ""
        raw_key_location = merged.get("key_location") or ""
        secret_candidate = self._extract_secret_candidate(
            sig_output.get("key_value"),
            merged.get("key_value"),
            merged.get("hypothesis"),
            merged.get("reasoning"),
            merged.get("analysis_notes"),
            raw_key_location,
        )
        endpoints = merged.get("api_endpoints") or merged.get("endpoints") or []
        if isinstance(endpoints, list):
            endpoints = self._dedupe_strings([self._repair_text(item) for item in endpoints if item])
        else:
            endpoints = []

        algorithm_id = self._normalize_algorithm_id(raw_algorithm)
        family_id = self._normalize_family_id(raw_family, algorithm_id)
        key_source = self._normalize_key_source(raw_key_source or ("hardcoded" if secret_candidate else ""))
        param_format = self._normalize_param_format(raw_param_format, request_fields)

        if algorithm_id == "unknown" and family_id == "unknown" and not param_format and key_source == "unknown" and not endpoints and not request_fields and not secret_candidate:
            return None

        signature_fields, fingerprint_fields, runtime_token_fields = self._derive_output_layers(request_fields, param_format)
        output_fields: dict[str, str] = {}
        output_fields.update(signature_fields)
        output_fields.update(runtime_token_fields)
        output_fields.update(fingerprint_fields)
        signing_inputs = [
            field for field in request_fields
            if field not in output_fields and not self._is_probable_fingerprint_field(field)
        ]

        canonical_steps: list[str] = []
        if algorithm_id != "unknown":
            canonical_steps.append(f"apply_{algorithm_id}")
        if key_source and key_source != "unknown":
            canonical_steps.append(f"key_source:{key_source}")
        if secret_candidate:
            canonical_steps.append("use_hardcoded_key")

        browser_dependencies: list[str] = []
        preferred_bridge_target = self._normalize_bridge_target(raw_key_location)
        if preferred_bridge_target:
            browser_dependencies.append(preferred_bridge_target)

        transport_url = ""
        transport_method = "GET"
        if primary_observed_request:
            transport_url = str(primary_observed_request.get("url") or "")
            transport_method = str(primary_observed_request.get("method") or "GET").upper()
        if not transport_url:
            transport_url = str((endpoints[0] if isinstance(endpoints, list) and endpoints else merged.get("page_url") or merged.get("url") or ""))

        codegen_strategy = "manual_required"
        if primary_observed_request and self._observed_request_prefers_replay(
            primary_observed_request,
            page_url=str(merged.get("page_url") or merged.get("url") or ""),
            output_fields=output_fields,
            secret_candidate=secret_candidate,
            algorithm_id=algorithm_id,
        ):
            codegen_strategy = "observed_replay"
        elif observed_requests and not secret_candidate and (
            output_fields or request_fields or algorithm_id in {"unknown", "fingerprint", "custom", "base64"}
        ):
            codegen_strategy = "observed_replay"
        elif secret_candidate or output_fields or algorithm_id != "unknown":
            codegen_strategy = "python_reconstruct"
        if preferred_bridge_target and not observed_requests:
            codegen_strategy = "js_bridge"
        transport_profile = {
            "method": transport_method,
            "url_pattern": transport_url,
        }
        normalization_rules = [
            "Prefer canonical crawler source emitted by code generation.",
            "Treat signature outputs as explicit fields defined by SignatureSpec.",
        ]
        if signature_fields:
            normalization_rules.append(f"Signature fields: {', '.join(list(signature_fields)[:6])}.")
        if fingerprint_fields:
            normalization_rules.append(f"Fingerprint fields: {', '.join(list(fingerprint_fields)[:6])}.")
        if runtime_token_fields:
            normalization_rules.append(f"Runtime token fields: {', '.join(list(runtime_token_fields)[:6])}.")
        if key_source and key_source != "unknown":
            normalization_rules.append(f"Key source classified as {key_source}.")
        if secret_candidate:
            normalization_rules.append("Recovered a hardcoded secret candidate from analysis evidence.")
        if request_fields:
            normalization_rules.append(f"Recovered request fields: {', '.join(request_fields[:8])}.")
        if algorithm_candidates:
            normalization_rules.append(f"Recovered algorithm hints: {', '.join(algorithm_candidates[:4])}.")
        if observed_requests:
            normalization_rules.append(f"Observed {len(observed_requests)} replay candidates from browser/network capture.")
        if primary_observed_request:
            normalization_rules.append("Focused SignatureSpec field inference on the primary observed target request.")

        return SignatureSpec(
            algorithm_id=algorithm_id,
            family_id=family_id,
            canonical_steps=canonical_steps,
            input_fields=signing_inputs,
            signing_inputs=signing_inputs,
            output_fields=output_fields,
            signing_outputs=signature_fields or output_fields,
            signature_fields=signature_fields,
            fingerprint_fields=fingerprint_fields,
            runtime_token_fields=runtime_token_fields,
            browser_dependencies=browser_dependencies,
            replay_requirements=[f"observed_request_count:{len(observed_requests)}"] if observed_requests else [],
            normalization_rules=normalization_rules,
            transport_profile=transport_profile,
            header_policy=self._derive_header_policy(request_fields, signature_fields, fingerprint_fields, runtime_token_fields),
            cookie_policy={"auth_mode": "unknown", "required": []},
            bridge_targets=[preferred_bridge_target] if preferred_bridge_target else [],
            preferred_bridge_target=preferred_bridge_target,
            bridge_mode="bridge_server" if preferred_bridge_target else "none",
            extractor_binding={},
            stability_level="standard",
            topology_summary=[],
            codegen_strategy=codegen_strategy,
            confidence=max(0.0, min(max(confidence, 0.25 if request_fields or secret_candidate or algorithm_candidates else 0.0), 1.0)),
        )

    def _build_crawler_source(self, merged: dict[str, Any]) -> dict[str, Any] | None:
        candidate = merged.get("crawler_source")
        if isinstance(candidate, dict) and candidate:
            normalized = dict(candidate)
            path = normalized.get("path") or normalized.get("crawler_path")
            python_code = str(normalized.get("python_code") or "")
            js_code = str(normalized.get("js_code") or "")
            if not python_code and path:
                python_code = self._read_text(path)
            if python_code or js_code:
                normalized["python_code"] = python_code
                normalized["js_code"] = js_code
                return normalized

        generated = merged.get("generated_model")
        if generated is not None:
            crawler_path = getattr(generated, "crawler_script_path", None)
            bridge_path = getattr(generated, "bridge_server_path", None)
            python_code = self._read_text(crawler_path)
            js_code = self._read_text(bridge_path)
            if python_code or js_code:
                return {
                    "source": "generated_model",
                    "path": str(crawler_path) if crawler_path else "",
                    "bridge_path": str(bridge_path) if bridge_path else "",
                    "python_code": python_code,
                    "js_code": js_code,
                    "output_mode": getattr(generated, "output_mode", ""),
                }

        python_code = str(merged.get("python_code") or "")
        js_code = str(merged.get("js_code") or "")
        if python_code.strip() or js_code.strip():
            return {
                "source": "codegen_output",
                "path": str(merged.get("crawler_path") or ""),
                "python_code": python_code,
                "js_code": js_code,
                "manifest": merged.get("manifest") or {},
            }

        code = str(merged.get("code") or "")
        if code.strip():
            return {
                "source": "ambient_code",
                "path": "",
                "python_code": code,
                "js_code": "",
            }
        return None

    @staticmethod
    def _merged_signature_hints(merged: dict[str, Any]) -> dict[str, Any]:
        combined: dict[str, Any] = {}
        sources = []
        for key in ("signature_extractor", "signature_extraction"):
            value = merged.get(key)
            if isinstance(value, dict):
                sources.append(value)
        sources.append(merged)

        for field in ("key_value", "algorithm", "key_source", "confidence", "param_format"):
            for source in sources:
                candidate = source.get(field)
                if candidate in (None, "", [], {}):
                    continue
                combined[field] = candidate
                break
        return combined

    def _debug_log(self, run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
        payload = {
            "sessionId": self.ctx.session_id or "unknown",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        try:
            with DEBUG_LOG_PATH.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    async def execute_tool(self, tool_name, input_data=None) -> ToolResult:
        tool = self.registry.get(tool_name)
        if not tool:
            log.error("tool_not_found", tool=tool_name)
            return ToolResult(tool_name=tool_name, status=ToolStatus.FAILED, error="Tool not found")

        merged_input = {**(input_data or {}), **self.state.context}

        try:
            if tool_name == "static":
                run_id = self.ctx.session_id or "run"
                self._debug_log(
                    run_id=run_id,
                    hypothesis_id="H2",
                    location="axelo/engine/executor.py:execute_tool",
                    message="about to run static tool",
                    data={
                        "has_js_code": bool((input_data or {}).get("js_code")),
                        "has_content": bool((input_data or {}).get("content")),
                        "bundles_count": len((input_data or {}).get("bundles") or []),
                        "input_keys": sorted(list((input_data or {}).keys())),
                    },
                )
            self.state.save_context_snapshot(tool_name)
            result = await tool.run(merged_input, self.state)
            if result.success:
                self.state.save_result(result)
                self.ctx.add_result(tool_name, result)
                log.info("tool_executed", tool=tool_name, status=result.status.value)
                if tool_name == "fetch":
                    run_id = self.ctx.session_id or "run"
                    self._debug_log(
                        run_id=run_id,
                        hypothesis_id="H3",
                        location="axelo/engine/executor.py:execute_tool",
                        message="fetch succeeded output shape",
                        data={
                            "output_keys": sorted(list((result.output or {}).keys())),
                            "content_len": len((result.output or {}).get("content") or ""),
                            "content_type": (result.output or {}).get("content_type"),
                        },
                    )
            else:
                log.warning("tool_failed", tool=tool_name, error=result.error)
                run_id = self.ctx.session_id or "run"
                self._debug_log(
                    run_id=run_id,
                    hypothesis_id="H4",
                    location="axelo/engine/executor.py:execute_tool",
                    message="tool execution failed",
                    data={"tool_name": tool_name, "error": result.error},
                )
            return result
        except Exception as exc:
            log.error("tool_execution_error", tool=tool_name, error=str(exc))
            return ToolResult(tool_name=tool_name, status=ToolStatus.FAILED, error=str(exc))

    def _build_input(self, tool_name, initial_input):
        merged = dict(initial_input)
        for _, prev_result in self.ctx.tool_results.items():
            if prev_result.success:
                merged.update(prev_result.output)
        if tool_name == "web_search" and not merged.get("query"):
            goal = str(merged.get("goal") or "").strip()
            url = str(merged.get("url") or "").strip()
            domain = ""
            if url:
                parsed = urlparse(url)
                domain = parsed.netloc or parsed.path
            query_parts = [part for part in [domain, goal] if part]
            if query_parts:
                merged["query"] = " ".join(query_parts).strip()
        if tool_name == "browser" and not merged.get("url"):
            results = merged.get("results") or []
            resolved_url = ""
            if isinstance(results, list) and results:
                first = results[0] if isinstance(results[0], dict) else {}
                resolved_url = str(first.get("url") or "").strip()
            if resolved_url:
                merged["url"] = resolved_url
        if tool_name == "fetch" and not merged.get("url"):
            page_url = str(merged.get("page_url") or "").strip()
            fallback_url = ""
            if page_url:
                fallback_url = page_url
            else:
                results = merged.get("results") or []
                if isinstance(results, list) and results:
                    first = results[0] if isinstance(results[0], dict) else {}
                    fallback_url = str(first.get("url") or "").strip()
            if fallback_url:
                merged["url"] = fallback_url
        if tool_name == "fetch_js_bundles":
            js_bundles = merged.get("js_bundles") or []
            if js_bundles:
                merged["urls"] = js_bundles
            elif not merged.get("urls") and merged.get("page_url"):
                merged["urls"] = [merged["page_url"]]
        if tool_name == "static":
            if not merged.get("js_code"):
                merged["js_code"] = self._collect_js_code(merged)
        if tool_name == "crypto":
            if not merged.get("js_code"):
                merged["js_code"] = self._collect_js_code(
                    merged,
                    bundle_limit=5,
                    bundle_bytes=50000,
                    fallback_bytes=120000,
                )
        if tool_name == "deobfuscate":
            if not merged.get("js_code"):
                merged["js_code"] = self._collect_js_code(
                    merged,
                    bundle_limit=3,
                    bundle_bytes=30000,
                    fallback_bytes=50000,
                )
        if tool_name == "trace":
            if not merged.get("js_code"):
                merged["js_code"] = self._collect_js_code(
                    merged,
                    bundle_limit=2,
                    bundle_bytes=20000,
                    fallback_bytes=50000,
                )
        if tool_name == "signature_extractor":
            if not merged.get("js_code"):
                merged["js_code"] = self._collect_js_code(
                    merged,
                    bundle_limit=5,
                    bundle_bytes=50000,
                    fallback_bytes=100000,
                )
            if not merged.get("api_endpoints"):
                api_endpoints = merged.get("api_endpoints") or merged.get("endpoints") or []
                if not api_endpoints:
                    static_output = merged.get("static") or {}
                    api_endpoints = static_output.get("api_endpoints") or static_output.get("endpoints") or []
                if api_endpoints:
                    merged["api_endpoints"] = api_endpoints
        if tool_name == "ai_analyze":
            if not merged.get("dynamic_analysis") and merged.get("dynamic_analysis"):
                merged["dynamic_analysis"] = merged.get("dynamic_analysis")
            if not merged.get("signature_extraction"):
                sig_output = self._merged_signature_hints(merged)
                if sig_output:
                    merged["signature_extraction"] = {
                        "key_value": sig_output.get("key_value"),
                        "algorithm": sig_output.get("algorithm"),
                        "key_source": sig_output.get("key_source"),
                        "confidence": sig_output.get("confidence"),
                        "param_format": sig_output.get("param_format"),
                    }
        if not merged.get("key_value"):
            secret_candidate = self._extract_secret_candidate(
                merged.get("hypothesis"),
                merged.get("reasoning"),
                merged.get("key_location"),
                merged.get("analysis_notes"),
            )
            if secret_candidate:
                merged["key_value"] = secret_candidate
                if not merged.get("key_source"):
                    merged["key_source"] = "hardcoded"
        signature_spec = self._build_signature_spec(merged)
        if signature_spec is not None:
            merged["signature_spec_model"] = signature_spec
            merged["signature_spec"] = signature_spec.model_dump(mode="json")
            if not merged.get("algorithm"):
                merged["algorithm"] = signature_spec.algorithm_id
            if not merged.get("signature_type"):
                merged["signature_type"] = signature_spec.family_id
        if tool_name == "codegen":
            if not merged.get("target_url"):
                merged["target_url"] = merged.get("page_url") or merged.get("url") or ""
            if not merged.get("extracted_key"):
                sig_output = self._merged_signature_hints(merged)
                if sig_output and sig_output.get("key_value"):
                    merged["extracted_key"] = {
                        "key_value": sig_output.get("key_value"),
                        "key_source": sig_output.get("key_source"),
                        "algorithm": sig_output.get("algorithm"),
                    }
            if not merged.get("hypothesis") and signature_spec is not None:
                merged["hypothesis"] = (
                    f"Reconstruct {signature_spec.family_id} signing flow using canonical SignatureSpec "
                    f"with algorithm {signature_spec.algorithm_id}."
                )
        if tool_name == "verify":
            if not merged.get("target_url"):
                merged["target_url"] = merged.get("page_url") or merged.get("url") or ""
            crawler_source = self._build_crawler_source(merged)
            if crawler_source is not None:
                merged["crawler_source"] = crawler_source
                python_code = str(crawler_source.get("python_code") or "")
                js_code = str(crawler_source.get("js_code") or "")
                if python_code.strip():
                    merged["python_code"] = python_code
                    merged["code"] = python_code
                elif js_code.strip():
                    merged["js_code"] = js_code
                    merged["code"] = js_code

        run_id = self.ctx.session_id or "run"
        self._debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="axelo/engine/executor.py:_build_input",
            message="built tool input",
            data={
                "tool_name": tool_name,
                "keys": sorted(list(merged.keys())),
                "has_js_code": bool(merged.get("js_code")),
                "has_content": bool(merged.get("content")),
                "bundles_count": len(merged.get("bundles") or []),
                "content_len": len(merged.get("content") or ""),
            },
        )
        return merged


    def get_state(self):
        return self.state

    def get_results(self):
        return self.ctx.tool_results

    def get_outputs(self):
        return self.ctx.get_all_outputs()

    def reset(self):
        self.state = ToolState()
        self.ctx = ExecutionContext()


def create_executor():
    return ToolExecutor()
