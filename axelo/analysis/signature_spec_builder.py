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
    output_fields = dict(hypothesis.outputs)
    canonical_steps = list(hypothesis.steps)
    topology_summary: list[str] = []
    bridge_targets: list[str] = []
    preferred_bridge_target: str | None = None

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
        topology_summary = list(dynamic.topology_summary)
        if dynamic.topologies:
            canonical_steps = list(dynamic.topologies[0].ordered_steps)
            output_fields = {
                item.sink_field: f"{item.sink_kind} sink derived from taint topology"
                for item in dynamic.topologies
                if item.sink_field
            } or output_fields
            for topology in dynamic.topologies:
                for step in topology.ordered_steps:
                    if "[" not in step:
                        browser_dependencies.add(step)
        bridge_targets = [
            item.name
            for item in dynamic.bridge_candidates
            if item.callable and item.name
        ]
        if dynamic.bridge_candidates:
            best_candidate = next(
                (item for item in dynamic.bridge_candidates if item.callable),
                dynamic.bridge_candidates[0],
            )
            preferred_bridge_target = best_candidate.name or None

    inferred_algorithm_id = _infer_algorithm_id(target, hypothesis)
    algorithm_id = inferred_algorithm_id if inferred_algorithm_id != "unknown" else (token_types[0] if token_types else "unknown")
    replay_requirements = []
    if target.known_endpoint:
        replay_requirements.append(f"Known endpoint: {target.known_endpoint}")
    if target.requires_login is True:
        replay_requirements.append("Requires authenticated session state")
    if target.antibot_type != "unknown":
        replay_requirements.append(f"Anti-bot context: {target.antibot_type}")

    codegen_strategy = hypothesis.codegen_strategy
    if (browser_dependencies or preferred_bridge_target) and codegen_strategy == "python_reconstruct":
        codegen_strategy = "js_bridge"

    return SignatureSpec(
        algorithm_id=algorithm_id,
        canonical_steps=canonical_steps,
        input_fields=sorted(set(hypothesis.inputs)),
        output_fields=output_fields,
        browser_dependencies=sorted(browser_dependencies),
        replay_requirements=replay_requirements,
        normalization_rules=[
            "Preserve header casing emitted by the generated crawler",
            "Treat timestamp and nonce fields as temporal values unless static evidence proves otherwise",
        ],
        bridge_targets=list(dict.fromkeys(bridge_targets)),
        preferred_bridge_target=preferred_bridge_target,
        topology_summary=topology_summary,
        codegen_strategy=codegen_strategy,
        confidence=hypothesis.confidence,
    )


def _infer_algorithm_id(target: TargetSite, hypothesis: AIHypothesis) -> str:
    template_name = (hypothesis.template_name or "").lower()
    notes = (hypothesis.notes or "").lower()
    description = (hypothesis.algorithm_description or "").lower()
    text = " ".join([template_name, notes, description])
    if "mtop" in text or any("/h5/mtop." in (request.url or "").lower() for request in (target.target_requests or target.captured_requests)):
        return "mtop"
    if "hmac" in text:
        return "hmac"
    if "md5" in text:
        return "md5"
    if "fingerprint" in text or "canvas" in text:
        return "fingerprint"
    return "unknown"
