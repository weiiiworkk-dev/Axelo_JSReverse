from __future__ import annotations

from urllib.parse import urlsplit

from axelo.analysis.request_contracts import derive_capability_profile
from axelo.models.analysis import AIHypothesis
from axelo.models.target import RequestCapture, TargetSite


HIGH_ENTROPY_HEADER_HINTS = (
    "x-csrf",
    "x-requested-with",
    "authorization",
    "token",
    "nonce",
    "signature",
    "sign",
    "sz-token",
    "af-ac-enc-",
    "x-sap-",
    "d-nonptcha-sync",
)


def build_hypothesis_from_observed_request(target: TargetSite) -> AIHypothesis:
    request = best_observed_request(target)
    if request is None:
        raise ValueError("No observed request is available for template-backed replay")

    contract = target.selected_contract
    capability = derive_capability_profile(target, contract=contract)
    outputs = {
        key: "observed request header replay"
        for key in (
            contract.required_headers
            if contract and contract.required_headers
            else _interesting_output_fields(request)
        )
    }
    steps = [
        "Load the persisted browser-backed session state captured during discovery.",
        "Replay the observed API request with the captured URL, method, and query layout.",
        "Reuse observed high-entropy headers directly when no callable signer is available.",
        "Attach same-site cookies from the persisted storage state before sending the request.",
        "Parse the response as JSON when possible and fall back to text diagnostics otherwise.",
    ]
    strategy = "js_bridge" if capability.needs_bridge or capability.needs_fingerprint else "python_reconstruct"
    return AIHypothesis(
        algorithm_description=(
            "Replay the observed request shape from captured traffic and preserve browser-derived "
            "headers or session state when no reusable signer function is available."
        ),
        generator_func_ids=[],
        steps=steps,
        inputs=["url", "method", "observed_headers", "storage_state"],
        outputs=outputs,
        family_id="plain_observed_replay",
        codegen_strategy=strategy,
        python_feasibility=0.8 if strategy == "python_reconstruct" else 0.45,
        confidence=0.78 if outputs else 0.7,
        notes=f"Observed replay template selected for {request.method} {request.url}",
        template_name="contract_replay",
        secret_candidate="",
    )


def best_observed_request(target: TargetSite) -> RequestCapture | None:
    requests = target.target_requests or target.captured_requests
    return requests[0] if requests else None


def request_supports_observed_replay(request: RequestCapture | None, *, page_url: str = "") -> bool:
    if request is None:
        return False
    url = (request.url or "").lower()
    headers = {str(key).lower(): str(value) for key, value in (request.request_headers or {}).items()}
    if not url.startswith(("http://", "https://")):
        return False
    if any(keyword in url for keyword in ("doubleclick", "/activity;", "/tracking", "/analytics")):
        return False
    if headers and any(_is_high_entropy_header(key) for key in headers):
        return True
    if request.method.upper() == "GET" and _same_site(url, page_url):
        return True
    return False


def _same_site(request_url: str, page_url: str) -> bool:
    request_host = urlsplit(request_url).hostname or ""
    page_host = urlsplit(page_url).hostname or ""
    if not request_host or not page_host:
        return False
    if request_host == page_host:
        return True
    page_suffix = page_host[4:] if page_host.startswith("www.") else page_host
    return bool(page_suffix and request_host.endswith(page_suffix))


def _interesting_output_fields(request: RequestCapture) -> list[str]:
    outputs: list[str] = []
    for key in (request.request_headers or {}).keys():
        lowered = str(key).lower()
        if _is_high_entropy_header(lowered) and key not in outputs:
            outputs.append(key)
    return outputs[:12]


def _is_high_entropy_header(key: str) -> bool:
    return any(hint in key for hint in HIGH_ENTROPY_HEADER_HINTS)
