from __future__ import annotations

from axelo.ai.agents.codegen_agent import _render_base_bridge_template, _render_base_crawler_template
from axelo.browser.simulation import build_context_options, build_simulation_payload, render_simulation_init_script
from axelo.models.target import BrowserProfile, TargetSite


def _target() -> TargetSite:
    return TargetSite(
        url="https://example.com/app",
        session_id="sim01",
        interaction_goal="visual regression",
    )


def test_build_context_options_include_rendering_fields():
    profile = BrowserProfile()
    options = build_context_options(profile)
    assert options["color_scheme"] == "light"
    assert options["reduced_motion"] == "no-preference"
    assert options["device_scale_factor"] == 1.0
    assert options["has_touch"] is False
    assert options["is_mobile"] is False
    assert options["extra_http_headers"]["Accept-Language"].startswith("zh-CN")


def test_simulation_payload_uses_runtime_keys():
    payload = build_simulation_payload(BrowserProfile())
    assert "environmentSimulation" in payload
    assert payload["environmentSimulation"]["profileName"] == "desktop"
    assert payload["interactionSimulation"]["pointer"]["defaultSeed"] >= 1
    assert payload["sessionRuntime"]["seed"] >= 1
    assert payload["runtimeHandles"]["envName"].startswith("__ax_env_")
    assert payload["browserIdentity"]["platform"] == "Win32"


def test_render_simulation_init_script_embeds_globals():
    script = render_simulation_init_script(BrowserProfile())
    assert "__AXELO_ENV__" not in script
    assert "__AXELO_INTERACTION__" not in script
    assert "__AXELO_SIMULATION_CONFIG__" not in script
    assert "__ax_env_" in script


def test_rendered_templates_include_simulation_interfaces():
    target = _target()
    bridge = _render_base_bridge_template(target, bridge_port=9123)
    crawler = _render_base_crawler_template(target, bridge_port=9123)

    assert "/environment/status" in bridge
    assert "/interaction/run-pointer-path" in bridge
    assert "/interaction/replay-pointer-trace" in bridge
    assert "/executor/discover" in bridge
    assert "/executor/invoke" in bridge
    assert "/wasm/modules" in bridge
    assert "/wasm/report" in bridge
    assert "/wasm/snapshots" in bridge
    assert "/wasm/invoke" in bridge
    assert "environmentSimulation" in crawler
    assert "interactionSimulation" in crawler
    assert "wasmTelemetry" in crawler
    assert "def invoke_function(" in crawler
    assert "def list_wasm_modules(" in crawler
    assert "def get_wasm_report(" in crawler
    assert "def get_wasm_snapshots(" in crawler
    assert "def invoke_wasm_export(" in crawler
