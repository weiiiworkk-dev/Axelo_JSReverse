from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from axelo.models.analysis import BridgeTargetCandidate, TaintEvent, TaintTopology
from axelo.models.target import RequestCapture

_FRAME_PATH_RE = re.compile(r"\bat\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)")
_IGNORE_FRAME_PARTS = {
    "__axelo",
    "window.fetch",
    "fetch",
    "XMLHttpRequest",
    "Headers.set",
    "Headers.append",
    "FormData.append",
    "URLSearchParams.append",
    "URLSearchParams.set",
    "JSON.stringify",
    "Promise",
}


class TopologyBuildResult(BaseModel):
    topologies: list[TaintTopology] = Field(default_factory=list)
    bridge_candidates: list[BridgeTargetCandidate] = Field(default_factory=list)
    topology_summary: list[str] = Field(default_factory=list)
    field_mapping: dict[str, str] = Field(default_factory=dict)


class TopologyBuilder:
    """Build taint topologies and reusable browser bridge candidates."""

    def build(self, events: list[TaintEvent], requests: list[RequestCapture]) -> TopologyBuildResult:
        if not events:
            return TopologyBuildResult()

        ordered_events = sorted(events, key=lambda item: (item.sequence, item.timestamp))
        events_by_taint: dict[str, list[TaintEvent]] = defaultdict(list)
        for event in ordered_events:
            for taint_id in event.taint_ids:
                events_by_taint[taint_id].append(event)

        topologies: list[TaintTopology] = []
        field_mapping: dict[str, str] = {}
        merged_candidates: dict[str, BridgeTargetCandidate] = {}

        for sink_event in [item for item in ordered_events if item.event_type == "sink" and item.sink]:
            chain = self._resolve_chain(sink_event, events_by_taint)
            ordered_steps = self._steps_for_chain(chain, sink_event)
            if not ordered_steps:
                continue

            candidates = self._bridge_candidates(chain, sink_event)
            for candidate in candidates:
                key = candidate.name or candidate.global_path or "|".join(candidate.evidence_frames[:1])
                existing = merged_candidates.get(key)
                if existing is None or candidate.score > existing.score:
                    merged_candidates[key] = candidate

            sink = sink_event.sink
            if sink is None:
                continue

            for event in chain:
                if event.api_name and event.event_type != "sink":
                    field_mapping.setdefault(event.api_name, sink.sink_field)

            topology = TaintTopology(
                sink_field=sink.sink_field or "<unknown>",
                sink_kind=sink.sink_kind,
                request_id=sink.request_id,
                request_url=sink.request_url or self._match_request_url(sink.request_method, requests),
                request_method=sink.request_method or "",
                ordered_steps=ordered_steps,
                taint_ids=list(dict.fromkeys(sink_event.taint_ids)),
                entrypoint_candidates=candidates,
                confidence=self._confidence(chain, sink_event),
            )
            topologies.append(topology)

        topology_summary = [self._summary_for_topology(item) for item in topologies]
        return TopologyBuildResult(
            topologies=topologies,
            bridge_candidates=sorted(
                merged_candidates.values(),
                key=lambda item: (-item.score, item.name, item.sink_field),
            ),
            topology_summary=topology_summary,
            field_mapping=field_mapping,
        )

    def render_mermaid(self, topologies: list[TaintTopology]) -> str:
        if not topologies:
            return "flowchart LR\n  empty[\"No taint topology captured\"]"

        lines = ["flowchart LR"]
        node_counter = 0
        for topo_index, topology in enumerate(topologies, 1):
            subgraph_name = f"topology_{topo_index}"
            lines.append(f"  subgraph {subgraph_name}[\"{self._escape_label(self._summary_for_topology(topology))}\"]")
            previous_node = None
            for step in topology.ordered_steps:
                node_counter += 1
                node_id = f"n{node_counter}"
                lines.append(f"    {node_id}[\"{self._escape_label(step)}\"]")
                if previous_node is not None:
                    lines.append(f"    {previous_node} --> {node_id}")
                previous_node = node_id
            lines.append("  end")
        return "\n".join(lines)

    def _resolve_chain(self, sink_event: TaintEvent, events_by_taint: dict[str, list[TaintEvent]]) -> list[TaintEvent]:
        visited_events: dict[int, TaintEvent] = {}
        for taint_id in sink_event.taint_ids:
            self._walk_taint(taint_id, sink_event.sequence, events_by_taint, visited_events)
        chain = sorted(visited_events.values(), key=lambda item: item.sequence)
        return [item for item in chain if item.event_type in {"source", "transform"}]

    def _walk_taint(
        self,
        taint_id: str,
        before_sequence: int,
        events_by_taint: dict[str, list[TaintEvent]],
        visited_events: dict[int, TaintEvent],
    ) -> None:
        source_event = self._latest_event_for_taint(taint_id, before_sequence, events_by_taint)
        if source_event is None:
            return
        if source_event.sequence in visited_events:
            return
        visited_events[source_event.sequence] = source_event
        for parent_id in source_event.parent_taint_ids:
            self._walk_taint(parent_id, source_event.sequence, events_by_taint, visited_events)

    def _latest_event_for_taint(
        self,
        taint_id: str,
        before_sequence: int,
        events_by_taint: dict[str, list[TaintEvent]],
    ) -> TaintEvent | None:
        for event in reversed(events_by_taint.get(taint_id, [])):
            if event.sequence < before_sequence and event.event_type in {"source", "transform"}:
                return event
        return None

    def _steps_for_chain(self, chain: list[TaintEvent], sink_event: TaintEvent) -> list[str]:
        steps: list[str] = []
        for event in chain:
            step = event.api_name.strip() if event.api_name else event.event_type
            if event.event_type == "source":
                rendered = step
            else:
                rendered = step
            if not steps or steps[-1] != rendered:
                steps.append(rendered)

        sink = sink_event.sink
        if sink:
            sink_label = sink.sink_field or "<unknown>"
            steps.append(f"{sink.sink_kind}[{sink_label}]")
        return steps

    def _bridge_candidates(self, chain: list[TaintEvent], sink_event: TaintEvent) -> list[BridgeTargetCandidate]:
        scores: dict[str, float] = defaultdict(float)
        frames_by_name: dict[str, list[str]] = defaultdict(list)

        weighted_events = list(chain[-3:]) + [sink_event]
        for offset, event in enumerate(weighted_events, 1):
            weight = 0.5 if event is sink_event else max(0.15, 0.45 - (len(weighted_events) - offset) * 0.1)
            for frame in event.stack_trace:
                candidate = self._candidate_from_frame(frame)
                if candidate is None:
                    continue
                scores[candidate["name"]] += weight
                frames_by_name[candidate["name"]].append(frame)
                if candidate["global_path"]:
                    scores[candidate["name"]] += 0.15

        sink_field = sink_event.sink.sink_field if sink_event.sink else ""
        candidates: list[BridgeTargetCandidate] = []
        for name, score in scores.items():
            sample = self._candidate_from_frame(frames_by_name[name][0])
            if sample is None:
                continue
            resolver_source = self._resolver_source(name) if score >= 0.75 else ""
            callable_candidate = bool(sample["global_path"] or resolver_source)
            candidates.append(
                BridgeTargetCandidate(
                    name=name,
                    global_path=sample["global_path"],
                    owner_path=sample["owner_path"],
                    resolver_source=resolver_source,
                    score=min(1.0, round(score, 3)),
                    callable=callable_candidate,
                    sink_field=sink_field,
                    evidence_frames=list(dict.fromkeys(frames_by_name[name]))[:5],
                )
            )
        return sorted(candidates, key=lambda item: (-item.score, item.name))[:5]

    def _candidate_from_frame(self, frame: str) -> dict[str, str] | None:
        if not frame:
            return None
        match = _FRAME_PATH_RE.search(frame)
        if not match:
            return None
        dotted = match.group(1).strip()
        lowered = dotted.lower()
        if any(part.lower() in lowered for part in _IGNORE_FRAME_PARTS):
            return None
        if "<anonymous>" in lowered or "native code" in lowered:
            return None
        global_path = dotted
        owner_path = dotted.rsplit(".", 1)[0] if "." in dotted else ""
        name = dotted.split(".")[-1]
        if len(name) < 2:
            return None
        return {
            "name": name,
            "global_path": global_path,
            "owner_path": owner_path,
        }

    def _resolver_source(self, fn_name: str) -> str:
        escaped = fn_name.replace("\\", "\\\\").replace("'", "\\'")
        return (
            "function resolveByName(options) {"
            f" const target = (options && options.name) || '{escaped}';"
            " const queue = [{ value: window, depth: 0 }];"
            " const seen = new Set();"
            " while (queue.length) {"
            "   const item = queue.shift();"
            "   if (!item || !item.value || (typeof item.value !== 'object' && typeof item.value !== 'function')) continue;"
            "   if (seen.has(item.value) || item.depth > 2) continue;"
            "   seen.add(item.value);"
            "   for (const key of Object.keys(item.value)) {"
            "     let next;"
            "     try { next = item.value[key]; } catch (_error) { continue; }"
            "     if (key === target && typeof next === 'function') return { fn: next, thisArg: item.value };"
            "     if (next && (typeof next === 'object' || typeof next === 'function')) queue.push({ value: next, depth: item.depth + 1 });"
            "   }"
            " }"
            " throw new Error('Unable to resolve function by name: ' + target);"
            "}"
        )

    def _confidence(self, chain: list[TaintEvent], sink_event: TaintEvent) -> float:
        distinct_sources = len({item.api_name for item in chain if item.event_type == "source"})
        distinct_transforms = len({item.api_name for item in chain if item.event_type == "transform"})
        base = 0.35 + min(0.2, distinct_sources * 0.1) + min(0.35, distinct_transforms * 0.12)
        if sink_event.sink and sink_event.sink.sink_field:
            base += 0.1
        if sink_event.stack_trace:
            base += 0.05
        return min(1.0, round(base, 3))

    def _summary_for_topology(self, topology: TaintTopology) -> str:
        return " -> ".join(topology.ordered_steps)

    def _escape_label(self, label: str) -> str:
        return label.replace('"', "'")

    def _match_request_url(self, method: str, requests: list[RequestCapture]) -> str:
        for request in requests:
            if not method or request.method == method:
                return request.url
        return requests[0].url if requests else ""
