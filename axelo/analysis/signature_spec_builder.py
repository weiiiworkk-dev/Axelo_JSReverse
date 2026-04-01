from __future__ import annotations

from axelo.models.analysis import AIHypothesis, DynamicAnalysis, StaticAnalysis
from axelo.models.signature import SignatureSpec
from axelo.models.target import TargetSite


def build_signature_spec(
    target: TargetSite,
    hypothesis: AIHypothesis,
    static_results: dict[str, StaticAnalysis],
    dynamic: DynamicAnalysis | None,
) -> SignatureSpec:
    token_types: list[str] = []
    browser_dependencies: set[str] = set()

    for static in static_results.values():
        for candidate in static.token_candidates:
            if candidate.func_id in hypothesis.generator_func_ids and candidate.token_type not in token_types:
                token_types.append(candidate.token_type)
        for env_key in static.env_access:
            lowered = env_key.lower()
            if any(signal in lowered for signal in ("canvas", "webgl", "fingerprint", "device", "subtle")):
                browser_dependencies.add(env_key)

    if dynamic:
        browser_dependencies.update(dynamic.crypto_primitives)

    algorithm_id = token_types[0] if token_types else "unknown"
    replay_requirements = []
    if target.known_endpoint:
        replay_requirements.append(f"Known endpoint: {target.known_endpoint}")
    if target.requires_login is True:
        replay_requirements.append("Requires authenticated session state")
    if target.antibot_type != "unknown":
        replay_requirements.append(f"Anti-bot context: {target.antibot_type}")

    codegen_strategy = hypothesis.codegen_strategy
    if browser_dependencies and codegen_strategy == "python_reconstruct":
        codegen_strategy = "js_bridge"

    return SignatureSpec(
        algorithm_id=algorithm_id,
        canonical_steps=hypothesis.steps,
        input_fields=sorted(set(hypothesis.inputs)),
        output_fields=hypothesis.outputs,
        browser_dependencies=sorted(browser_dependencies),
        replay_requirements=replay_requirements,
        normalization_rules=[
            "Preserve header casing emitted by the generated crawler",
            "Treat timestamp and nonce fields as temporal values unless static evidence proves otherwise",
        ],
        codegen_strategy=codegen_strategy,
        confidence=hypothesis.confidence,
    )
