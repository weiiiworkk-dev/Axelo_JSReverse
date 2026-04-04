from __future__ import annotations

from axelo.models.analysis import (
    BridgeTargetCandidate,
    DynamicAnalysis,
    HookIntercept,
    TaintEvent,
    TaintTopology,
)
from axelo.models.target import RequestCapture


class TraceBuilder:
    """
    Combine legacy hook intercepts with taint topology so downstream stages
    can consume a single runtime analysis payload.
    """

    def build(
        self,
        bundle_id: str,
        intercepts: list[HookIntercept],
        target_requests: list[RequestCapture],
        hook_analysis: dict,
        taint_events: list[TaintEvent] | None = None,
        topologies: list[TaintTopology] | None = None,
        bridge_candidates: list[BridgeTargetCandidate] | None = None,
        topology_summary: list[str] | None = None,
    ) -> DynamicAnalysis:
        taint_events = taint_events or []
        topologies = topologies or []
        bridge_candidates = bridge_candidates or []
        topology_summary = topology_summary or []
        if not intercepts and not taint_events and not target_requests:
            return DynamicAnalysis(bundle_id=bundle_id)

        requests = [request for request in target_requests if request.timestamp > 0]
        if requests:
            first_target_ts = min(request.timestamp for request in requests)
        elif intercepts:
            first_target_ts = max(item.timestamp for item in intercepts) + 5.0
        elif taint_events:
            first_target_ts = max(item.timestamp for item in taint_events) + 5.0
        else:
            return DynamicAnalysis(bundle_id=bundle_id)

        pre_request_intercepts = [
            intercept
            for intercept in intercepts
            if 0 < intercept.timestamp <= first_target_ts and (first_target_ts - intercept.timestamp) <= 5.0
        ]
        pre_request_events = [
            event
            for event in taint_events
            if 0 < event.timestamp <= first_target_ts and (first_target_ts - event.timestamp) <= 5.0
        ]

        from axelo.analysis.dynamic.hook_analyzer import HIGH_VALUE_APIS

        confirmed_generators: list[str] = []
        crypto_primitives: list[str] = []
        for intercept in pre_request_intercepts:
            if intercept.api_name in HIGH_VALUE_APIS:
                crypto_primitives.append(intercept.api_name)
                for frame in intercept.stack_trace:
                    if frame and "axelo" not in frame.lower():
                        confirmed_generators.append(frame.strip())
                        break

        for topology in topologies:
            confirmed_generators.extend(
                candidate.name
                for candidate in topology.entrypoint_candidates
                if candidate.callable and candidate.name
            )
            for step in topology.ordered_steps:
                if "[" not in step:
                    crypto_primitives.append(step)

        return DynamicAnalysis(
            bundle_id=bundle_id,
            hook_intercepts=pre_request_intercepts,
            taint_events=pre_request_events or taint_events,
            topologies=topologies,
            bridge_candidates=bridge_candidates,
            topology_summary=topology_summary,
            confirmed_generators=list(dict.fromkeys(confirmed_generators)),
            field_mapping=hook_analysis.get("field_mapping", {}),
            crypto_primitives=list(dict.fromkeys(crypto_primitives)),
        )
