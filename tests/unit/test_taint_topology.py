from __future__ import annotations

import json

from axelo.analysis.dynamic.topology_builder import TopologyBuilder
from axelo.analysis.signature_spec_builder import build_signature_spec
from axelo.browser.bridge_client import BridgeClient
from axelo.browser.hooks import JSHookInjector
from axelo.models.analysis import (
    AIHypothesis,
    BridgeTargetCandidate,
    DynamicAnalysis,
    StaticAnalysis,
    TaintEvent,
    TaintSink,
    TaintTopology,
    TokenCandidate,
)
from axelo.models.target import TargetSite


def _target() -> TargetSite:
    return TargetSite(
        url="https://example.com/app",
        session_id="topo01",
        interaction_goal="collect signed headers",
    )


def test_topology_builder_builds_collapsed_chain_and_candidates():
    builder = TopologyBuilder()
    events = [
        TaintEvent(
            event_type="source",
            api_name="Date.now",
            taint_ids=["t1"],
            sequence=1,
            timestamp=1.0,
            stack_trace=["at signPayload (app.js:10:2)"],
        ),
        TaintEvent(
            event_type="transform",
            api_name="window.btoa",
            taint_ids=["t2"],
            parent_taint_ids=["t1"],
            sequence=2,
            timestamp=2.0,
            stack_trace=["at signPayload (app.js:11:2)"],
        ),
        TaintEvent(
            event_type="transform",
            api_name="window.btoa",
            taint_ids=["t3"],
            parent_taint_ids=["t2"],
            sequence=3,
            timestamp=3.0,
            stack_trace=["at signPayload (app.js:12:2)"],
        ),
        TaintEvent(
            event_type="transform",
            api_name="crypto.subtle.digest",
            taint_ids=["t4"],
            parent_taint_ids=["t3"],
            sequence=4,
            timestamp=4.0,
            stack_trace=["at security.signPayload (app.js:20:2)"],
        ),
        TaintEvent(
            event_type="sink",
            api_name="window.fetch",
            taint_ids=["t4"],
            sequence=5,
            timestamp=5.0,
            stack_trace=["at security.signPayload (app.js:25:2)"],
            sink=TaintSink(
                request_id="req_1",
                sink_field="x-sign",
                sink_kind="header",
                request_url="https://example.com/api",
                request_method="POST",
            ),
        ),
    ]

    result = builder.build(events, [])

    assert result.topology_summary == [
        "Date.now -> window.btoa -> crypto.subtle.digest -> header[x-sign]"
    ]
    assert result.topologies[0].ordered_steps == [
        "Date.now",
        "window.btoa",
        "crypto.subtle.digest",
        "header[x-sign]",
    ]
    assert any(candidate.name == "signPayload" for candidate in result.bridge_candidates)
    assert any(candidate.callable for candidate in result.bridge_candidates)


def test_signature_spec_prefers_topology_and_bridge_candidates():
    target = _target()
    static_results = {
        "bundle": StaticAnalysis(
            bundle_id="bundle",
            token_candidates=[
                TokenCandidate(
                    func_id="bundle:sign",
                    token_type="hmac",
                    confidence=0.9,
                    request_field="x-sign",
                )
            ],
        )
    }
    dynamic = DynamicAnalysis(
        bundle_id="bundle",
        topologies=[
            TaintTopology(
                sink_field="x-sign",
                sink_kind="header",
                request_id="req_1",
                ordered_steps=[
                    "Date.now",
                    "window.btoa",
                    "crypto.subtle.digest",
                    "header[x-sign]",
                ],
                taint_ids=["t4"],
            )
        ],
        bridge_candidates=[
            BridgeTargetCandidate(
                name="signPayload",
                global_path="security.signPayload",
                owner_path="security",
                score=0.91,
                callable=True,
                sink_field="x-sign",
            )
        ],
        topology_summary=["Date.now -> window.btoa -> crypto.subtle.digest -> header[x-sign]"],
        crypto_primitives=["crypto.subtle.digest"],
    )
    hypothesis = AIHypothesis(
        algorithm_description="fallback description",
        generator_func_ids=["bundle:sign"],
        steps=["guess 1", "guess 2"],
        inputs=["body"],
        outputs={"prior-sign": "old field"},
        codegen_strategy="python_reconstruct",
        confidence=0.7,
    )

    spec = build_signature_spec(target, hypothesis, static_results, dynamic)

    assert spec.canonical_steps == [
        "Date.now",
        "window.btoa",
        "crypto.subtle.digest",
        "header[x-sign]",
    ]
    assert spec.output_fields == {"x-sign": "header sink derived from taint topology"}
    assert spec.preferred_bridge_target == "signPayload"
    assert spec.bridge_targets == ["signPayload"]
    assert spec.codegen_strategy == "js_bridge"
    assert spec.topology_summary == ["Date.now -> window.btoa -> crypto.subtle.digest -> header[x-sign]"]


def test_bridge_client_uses_executor_endpoints():
    client = BridgeClient("http://127.0.0.1:9999")
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method: str, path: str, payload=None, *, timeout=None):
        calls.append((method, path, payload))
        if path.startswith("/executor/discover"):
            return {"candidates": [{"name": "signPayload"}]}
        if path == "/executor/invoke":
            return {"result": {"headers": {"x-sign": "abc"}}}
        if path == "/bridge/register":
            return {"ok": True}
        if path == "/wasm/modules":
            return {"modules": [{"moduleId": "wasm-module-1"}]}
        if path.startswith("/wasm/report"):
            return {"moduleId": "wasm-module-1", "artifactPaths": {"report": "module.report.json"}}
        if path.startswith("/wasm/snapshots"):
            return {"snapshots": [{"snapshotId": 3, "instanceId": "wasm-instance-1"}]}
        if path == "/wasm/invoke":
            return {"moduleId": "wasm-module-1", "result": {"ok": True}}
        return {}

    client.request = fake_request  # type: ignore[method-assign]

    assert client.discover_functions(min_score=0.8) == [{"name": "signPayload"}]
    assert client.invoke_function("signPayload", [{"body": "1"}]) == {"headers": {"x-sign": "abc"}}
    register = client.register_function("signPayload", global_path="security.signPayload")
    assert client.list_wasm_modules() == [{"moduleId": "wasm-module-1"}]
    assert client.get_wasm_report("wasm-module-1") == {"moduleId": "wasm-module-1", "artifactPaths": {"report": "module.report.json"}}
    assert client.get_wasm_snapshots(instance_id="wasm-instance-1", since=2) == [{"snapshotId": 3, "instanceId": "wasm-instance-1"}]
    assert client.invoke_wasm_export(
        export_name="sign",
        module_id="wasm-module-1",
        args=[1, 2],
        buffer_descriptors=[{"name": "input", "role": "input", "ptrArgIndex": 0, "lenArgIndex": 1}],
    ) == {"moduleId": "wasm-module-1", "result": {"ok": True}}

    assert register == {"ok": True}
    assert calls[0][1].startswith("/executor/discover")
    assert calls[1] == (
        "POST",
        "/executor/invoke",
        {"name": "signPayload", "args": [{"body": "1"}], "autoRegister": True},
    )
    assert calls[2] == (
        "POST",
        "/bridge/register",
        {
            "name": "signPayload",
            "globalPath": "security.signPayload",
            "ownerPath": None,
            "resolverSource": None,
            "resolverArg": None,
        },
    )
    assert calls[3] == ("GET", "/wasm/modules", None)
    assert calls[4] == ("GET", "/wasm/report?moduleId=wasm-module-1", None)
    assert calls[5] == ("GET", "/wasm/snapshots?since=2&instanceId=wasm-instance-1", None)
    assert calls[6] == (
        "POST",
        "/wasm/invoke",
        {
            "moduleId": "wasm-module-1",
            "instanceId": None,
            "exportName": "sign",
            "args": [1, 2],
            "bufferDescriptors": [{"name": "input", "role": "input", "ptrArgIndex": 0, "lenArgIndex": 1}],
            "captureMemory": True,
            "snapshotMode": None,
        },
    )


def test_js_hook_injector_collects_raw_and_taint_events():
    injector = JSHookInjector()
    injector._on_hook_fired(
        {},
        "raw_call",
        json.dumps(
            {
                "sequence": 1,
                "timestamp": 1.0,
                "api_name": "Date.now",
                "args_json": "[]",
                "return_json": "1700000000000",
                "stack_trace": ["at signPayload (app.js:1:1)"],
            }
        ),
    )
    injector._on_hook_fired(
        {},
        "sink",
        json.dumps(
            {
                "sequence": 2,
                "timestamp": 2.0,
                "api_name": "window.fetch",
                "taint_ids": ["t1"],
                "parent_taint_ids": [],
                "stack_trace": ["at signPayload (app.js:2:1)"],
                "value_preview": '"abc"',
                "sink": {
                    "request_id": "req_1",
                    "sink_field": "x-sign",
                    "sink_kind": "header",
                    "request_url": "https://example.com/api",
                    "request_method": "POST",
                },
            }
        ),
    )

    assert len(injector.get_intercepts()) == 1
    assert len(injector.get_taint_events()) == 1
    assert injector.get_taint_events()[0].sink is not None
    assert injector.get_taint_events()[0].sink.sink_field == "x-sign"
