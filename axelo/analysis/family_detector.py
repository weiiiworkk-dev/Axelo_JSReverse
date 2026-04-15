from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, Field

from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.target import TargetSite


class SignatureFamilyMatch(BaseModel):
    family_id: str = "unknown"
    algorithm_type: str = "unknown"
    confidence: float = 0.0
    source: str = "heuristic"
    template_name: str = ""
    template_ready: bool = False
    codegen_strategy: str = "js_bridge"
    generator_func_ids: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    notes: str = ""
    secret_candidate: str = ""


def detect_signature_family(
    target: TargetSite,
    static_results: dict[str, StaticAnalysis],
    dynamic: DynamicAnalysis | None = None,
    memory_ctx: dict | None = None,
    templates: Iterable[object] | None = None,
) -> SignatureFamilyMatch:
    memory_ctx = memory_ctx or {}
    known_pattern = memory_ctx.get("known_pattern") or {}
    known_algo = ""
    if known_pattern and (known_pattern.get("verified") or known_pattern.get("success_count", 0) > 0):
        known_algo = (known_pattern.get("algorithm_type") or "").lower()
    available_templates = list(templates or [])

    token_types: list[str] = []
    request_fields: dict[str, str] = {}
    generator_func_ids: list[str] = []
    crypto_imports: set[str] = set()
    env_access: set[str] = set()
    string_constants: list[str] = []

    for static in static_results.values():
        crypto_imports.update(item.lower() for item in static.crypto_imports)
        env_access.update(item.lower() for item in static.env_access)
        string_constants.extend(static.string_constants)
        for candidate in static.token_candidates:
            lowered = candidate.token_type.lower()
            if lowered not in token_types:
                token_types.append(lowered)
            if candidate.request_field:
                request_fields[candidate.request_field] = lowered
            if candidate.func_id not in generator_func_ids:
                generator_func_ids.append(candidate.func_id)

    if dynamic:
        crypto_imports.update(item.lower() for item in dynamic.crypto_primitives)

    if known_algo:
        match = _build_match(
            family_id=_family_id_for_algorithm(known_algo, env_access),
            algorithm_type=known_algo,
            confidence=0.93,
            source="memory_pattern",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )
        if match.family_id != "unknown":
            return match

    if _is_fingerprint(env_access, token_types, crypto_imports):
        return _build_match(
            family_id="canvas-fingerprint-bridge",
            algorithm_type="fingerprint",
            confidence=0.88,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if _is_mtop_h5_signing(target, request_fields):
        return _build_match(
            family_id="mtop-h5-token",
            algorithm_type="mtop",
            confidence=0.9,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if _is_cookie_bound_signing(target, request_fields, string_constants):
        return _build_match(
            family_id="cookie-bound-md5",
            algorithm_type="cookie_md5",
            confidence=0.91,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if "hmac" in token_types or "hmac" in crypto_imports or "sha256" in token_types:
        return _build_match(
            family_id="hmac-sha256-timestamp",
            algorithm_type="hmac",
            confidence=0.86 if _has_temporal_fields(request_fields) else 0.78,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if "md5" in token_types or "md5" in crypto_imports:
        return _build_match(
            family_id="md5-params-salt",
            algorithm_type="md5",
            confidence=0.82,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if "rsa" in token_types or "rsa" in crypto_imports:
        return _build_match(
            family_id="rsa-wrapper",
            algorithm_type="rsa",
            confidence=0.7,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    if "aes" in token_types or "aes" in crypto_imports:
        return _build_match(
            family_id="aes-wrapper",
            algorithm_type="aes",
            confidence=0.7,
            source="heuristic",
            generator_func_ids=generator_func_ids,
            request_fields=request_fields,
            env_access=env_access,
            string_constants=string_constants,
            templates=available_templates,
        )

    return SignatureFamilyMatch()


def build_hypothesis_from_family(match: SignatureFamilyMatch, target: TargetSite) -> AIHypothesis:
    del target
    notes = match.notes
    if match.template_name:
        notes = f"{notes}\nTemplate: {match.template_name}".strip()
    return AIHypothesis(
        algorithm_description=_description_for_family(match),
        generator_func_ids=match.generator_func_ids,
        steps=match.steps or _default_steps(match.algorithm_type),
        inputs=match.inputs or _default_inputs(match.algorithm_type),
        outputs=match.outputs,
        family_id=match.family_id,
        codegen_strategy="python_reconstruct" if match.codegen_strategy != "js_bridge" else "js_bridge",
        python_feasibility=0.9 if match.codegen_strategy != "js_bridge" else 0.2,
        confidence=match.confidence,
        notes=notes,
        template_name=match.template_name,
        secret_candidate=match.secret_candidate,
    )


def _build_match(
    *,
    family_id: str,
    algorithm_type: str,
    confidence: float,
    source: str,
    generator_func_ids: list[str],
    request_fields: dict[str, str],
    env_access: set[str],
    string_constants: list[str],
    templates: list[object],
) -> SignatureFamilyMatch:
    template_name = _pick_template_name(family_id, algorithm_type, templates)
    secret_candidate = _pick_secret_candidate(string_constants, algorithm_type)
    codegen_strategy = "js_bridge" if algorithm_type in {"fingerprint", "rsa", "aes", "cookie_md5", "mtop"} else "python_reconstruct"
    template_ready = bool(template_name) and (algorithm_type == "fingerprint" or bool(secret_candidate))
    return SignatureFamilyMatch(
        family_id=family_id,
        algorithm_type=algorithm_type,
        confidence=confidence,
        source=source,
        template_name=template_name,
        template_ready=template_ready,
        codegen_strategy=codegen_strategy,
        generator_func_ids=generator_func_ids[:4],
        inputs=_default_inputs(algorithm_type),
        outputs=_outputs_from_request_fields(request_fields, algorithm_type),
        steps=_default_steps(algorithm_type),
        notes=_notes_for_match(algorithm_type, env_access, secret_candidate),
        secret_candidate=secret_candidate,
    )


def _family_id_for_algorithm(algorithm_type: str, env_access: set[str]) -> str:
    if algorithm_type == "fingerprint" or _is_fingerprint(env_access, [], set()):
        return "canvas-fingerprint-bridge"
    if algorithm_type == "mtop":
        return "mtop-h5-token"
    if algorithm_type == "cookie_md5":
        return "cookie-bound-md5"
    if algorithm_type == "hmac":
        return "hmac-sha256-timestamp"
    if algorithm_type == "md5":
        return "md5-params-salt"
    if algorithm_type:
        return f"{algorithm_type}-wrapper"
    return "unknown"


def _is_fingerprint(env_access: set[str], token_types: list[str], crypto_imports: set[str]) -> bool:
    joined = " ".join(sorted(env_access | crypto_imports))
    if "fingerprint" in token_types:
        return True
    return any(signal in joined for signal in ("canvas", "webgl", "fingerprint", "device"))


def _has_temporal_fields(request_fields: dict[str, str]) -> bool:
    haystack = " ".join(f"{key}:{value}" for key, value in request_fields.items()).lower()
    return any(signal in haystack for signal in ("timestamp", "nonce", "ts", "x-t"))


def _pick_template_name(family_id: str, algorithm_type: str, templates: list[object]) -> str:
    for template in templates:
        if getattr(template, "name", "") == family_id:
            return template.name
    for template in templates:
        if getattr(template, "algorithm_type", "") == algorithm_type:
            return template.name
    return ""


def _pick_secret_candidate(string_constants: list[str], algorithm_type: str) -> str:
    if algorithm_type not in {"hmac", "md5"}:
        return ""
    candidates = []
    for item in string_constants:
        if not item or len(item) < 8 or len(item) > 96:
            continue
        if item.startswith("http") or "/" in item or " " in item:
            continue
        if re.fullmatch(r"[A-Za-z0-9_+=/\-]{8,96}", item):
            candidates.append(item)
    candidates.sort(key=len, reverse=True)
    return candidates[0] if candidates else ""


def _outputs_from_request_fields(request_fields: dict[str, str], algorithm_type: str) -> dict[str, str]:
    if algorithm_type == "cookie_md5":
        if request_fields:
            return {key: f"{value} derived signing field" for key, value in request_fields.items()}
        return {"sign": "cookie-bound signing digest", "t": "request timestamp"}
    if algorithm_type == "mtop":
        return {
            "sign": "MTOP request signature",
            "t": "request timestamp",
            "data": "serialized request payload",
            "appKey": "MTOP application key",
        }
    if request_fields:
        return {
            key: f"{value} derived signing field" if value != "unknown" else "derived signing field"
            for key, value in request_fields.items()
        }
    if algorithm_type == "fingerprint":
        return {"X-Device-ID": "browser fingerprint", "X-Fp": "secondary fingerprint digest"}
    if algorithm_type == "hmac":
        return {"X-Sign": "HMAC digest", "X-Timestamp": "request timestamp"}
    if algorithm_type == "md5":
        return {"sign": "MD5 signature"}
    return {}


def _default_inputs(algorithm_type: str) -> list[str]:
    if algorithm_type == "cookie_md5":
        return ["url", "method", "body", "cookies", "app_key"]
    if algorithm_type == "mtop":
        return ["token_cookie", "appKey", "t", "data", "api", "version"]
    if algorithm_type == "hmac":
        return ["url", "method", "body", "timestamp", "nonce", "secret_key"]
    if algorithm_type == "md5":
        return ["params", "salt"]
    if algorithm_type == "fingerprint":
        return ["browser_context"]
    return ["url", "method", "body"]


def _default_steps(algorithm_type: str) -> list[str]:
    if algorithm_type == "cookie_md5":
        return [
            "Read the session token cookie from the active browser session.",
            "Extract the token prefix and the current timestamp query parameter.",
            "Build the canonical signing payload from the observed token, timestamp, app key, and request data.",
            "Replay the request through the browser-backed signer so session cookies remain consistent.",
        ]
    if algorithm_type == "mtop":
        return [
            "Recover the current H5 token cookie from the browser session.",
            "Preserve the observed appKey, timestamp, and serialized data payload.",
            "Delegate signing to the browser-side MTOP flow instead of reconstructing it in Python.",
            "Replay the request through the bridge so token rotation remains aligned.",
        ]
    if algorithm_type == "hmac":
        return [
            "Read the current timestamp and optional nonce.",
            "Build a canonical signing string from the request URL, method, body, and temporal fields.",
            "Apply HMAC-SHA256 with the extracted secret material.",
            "Attach the digest and temporal headers to the outgoing request.",
        ]
    if algorithm_type == "md5":
        return [
            "Normalize request parameters into a deterministic string.",
            "Append the observed salt or suffix value.",
            "Compute the MD5 digest and attach it to the request.",
        ]
    if algorithm_type == "fingerprint":
        return [
            "Collect browser-rendering fingerprint signals from canvas or WebGL.",
            "Serialize the fingerprint payload in the expected header format.",
            "Attach the fingerprint headers before replaying the request.",
        ]
    return [
        "Normalize the observed request inputs.",
        "Apply the inferred signing transform.",
        "Attach the derived fields to the outgoing request.",
    ]


def _notes_for_match(algorithm_type: str, env_access: set[str], secret_candidate: str) -> str:
    notes = []
    if secret_candidate:
        notes.append(f"Extracted reusable secret candidate: {secret_candidate[:24]}")
    if algorithm_type == "cookie_md5":
        notes.append("Observed cookie-bound request signing; session cookie is part of the signing payload — use browser bridge mode.")
    if algorithm_type == "mtop":
        notes.append("Observed MTOP H5 request pattern; preserve browser token state and sign through the JS bridge.")
    if algorithm_type == "fingerprint" and env_access:
        notes.append(f"Observed browser dependencies: {', '.join(sorted(env_access)[:5])}")
    return "\n".join(notes)


def _description_for_family(match: SignatureFamilyMatch) -> str:
    if match.algorithm_type == "cookie_md5":
        return "Generate signing fields from session cookies and request parameters using MD5, then replay requests through the browser bridge to keep cookies consistent."
    if match.algorithm_type == "mtop":
        return "Replay the MTOP H5 flow through the browser bridge so token cookie rotation, timestamp, and sign fields stay aligned with the site runtime."
    if match.algorithm_type == "hmac":
        return "Generate request headers by applying HMAC-SHA256 to a canonical string built from the request inputs and temporal fields."
    if match.algorithm_type == "md5":
        return "Generate a deterministic request signature by hashing normalized parameters plus an observed salt with MD5."
    if match.algorithm_type == "fingerprint":
        return "Generate browser-derived fingerprint headers from canvas/WebGL signals and attach them to the request."
    return f"Generate signing fields using the detected {match.algorithm_type or 'custom'} request-signing family."


def _is_cookie_bound_signing(
    target: TargetSite,
    request_fields: dict[str, str],
    string_constants: list[str],
) -> bool:
    """Detect any protocol where a session cookie is part of the signing payload.

    This is a structural pattern: sign + timestamp + app_key + request_data,
    where the signing key is derived from a rotating session cookie.
    It applies generically to any site using this scheme — not tied to any
    specific platform.
    """
    # Signal 1: string constants mention a cookie-derived token pattern
    joined_strings = " ".join(item.lower() for item in string_constants)
    cookie_token_signals = any(
        pattern in joined_strings
        for pattern in ("_tk", "h5_tk", "cookie_sign", "cookie_token", "session_token", "token_sign")
    )
    if cookie_token_signals:
        return True

    # Signal 2: request URL has sign + timestamp + data + app_key — cookie-bound signing signature
    requests = target.target_requests or target.captured_requests
    for request in requests[:8]:
        parsed = urlsplit(request.url or "")
        query = {key.lower() for key in parse_qs(parsed.query).keys()}
        has_sign_ts_data = {"sign", "t", "data"}.issubset(query)
        has_app_key = any(k in query for k in ("appkey", "app_key", "apikey", "api_key", "appid"))
        if has_sign_ts_data and has_app_key:
            return True

    # Signal 3: all three signing fields present in request_fields
    lowered_fields = {key.lower() for key in request_fields.keys()}
    return {"sign", "t", "data"}.issubset(lowered_fields)


def _is_mtop_h5_signing(target: TargetSite, request_fields: dict[str, str]) -> bool:
    requests = target.target_requests or target.captured_requests
    for request in requests[:8]:
        parsed = urlsplit(request.url or "")
        path = parsed.path.lower()
        query = {key.lower() for key in parse_qs(parsed.query).keys()}
        if "/h5/mtop." in path and {"sign", "t", "data"}.issubset(query):
            return True
    lowered_fields = {key.lower() for key in request_fields.keys()}
    return "appkey" in lowered_fields and {"sign", "t", "data"}.issubset(lowered_fields)
