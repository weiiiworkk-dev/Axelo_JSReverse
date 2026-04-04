from __future__ import annotations

from axelo.models.analysis import HookIntercept, StaticAnalysis, TaintEvent, TaintTopology


HIGH_VALUE_APIS = {
    "crypto.subtle.sign",
    "crypto.subtle.digest",
    "crypto.subtle.encrypt",
    "crypto.getRandomValues",
    "window.btoa",
}


class HookAnalyzer:
    """
    Summarize legacy hook intercepts and fold topology-derived sink mapping into
    a compact runtime analysis report.
    """

    def analyze(
        self,
        intercepts: list[HookIntercept],
        static: StaticAnalysis | None = None,
        *,
        taint_events: list[TaintEvent] | None = None,
        topologies: list[TaintTopology] | None = None,
    ) -> dict:
        taint_events = taint_events or []
        topologies = topologies or []
        if not intercepts and not taint_events and not topologies:
            return {
                "apis_called": [],
                "high_value": [],
                "field_mapping": {},
                "summary": "No hook activity",
            }

        api_counts: dict[str, int] = {}
        for intercept in intercepts:
            api_counts[intercept.api_name] = api_counts.get(intercept.api_name, 0) + 1
        for event in taint_events:
            if event.api_name:
                api_counts[event.api_name] = api_counts.get(event.api_name, 0) + 1

        apis_called = sorted(api_counts.keys(), key=lambda key: (-api_counts[key], key))
        high_value = [api for api in apis_called if api in HIGH_VALUE_APIS]

        field_mapping: dict[str, str] = {}
        if static:
            for candidate in static.token_candidates:
                for intercept in intercepts:
                    if candidate.request_field and _apis_related(intercept.api_name, candidate.token_type):
                        field_mapping[intercept.api_name] = candidate.request_field

        for topology in topologies:
            for step in topology.ordered_steps:
                if "[" in step:
                    continue
                field_mapping.setdefault(step, topology.sink_field)

        summary_parts = [f"{api}x{count}" for api, count in api_counts.items()]
        summary = "Hook calls: " + ", ".join(summary_parts[:8]) if summary_parts else "Hook calls: none"
        if topologies:
            summary += f"\nTopologies: {len(topologies)}"

        return {
            "apis_called": apis_called,
            "high_value": high_value,
            "api_counts": api_counts,
            "field_mapping": field_mapping,
            "summary": summary,
        }


def _apis_related(api_name: str, token_type: str) -> bool:
    mapping = {
        "hmac": ["crypto.subtle.sign"],
        "sha256": ["crypto.subtle.digest"],
        "aes": ["crypto.subtle.encrypt", "crypto.subtle.decrypt"],
        "base64": ["window.btoa", "window.atob"],
    }
    return api_name in mapping.get(token_type, [])
