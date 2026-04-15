from __future__ import annotations

from axelo.engine.executor import ToolExecutor
from axelo.tools.base import ToolResult, ToolStatus


def test_executor_builds_signature_extractor_input_from_bundles_and_static_outputs():
    executor = ToolExecutor()
    executor.ctx.add_result(
        "fetch_js_bundles",
        ToolResult(
            tool_name="fetch_js_bundles",
            status=ToolStatus.SUCCESS,
            output={"bundles": [{"url": "https://example.com/app.js", "content": "const key='1234567890abcdef';"}]},
        ),
    )
    executor.ctx.add_result(
        "static",
        ToolResult(
            tool_name="static",
            status=ToolStatus.SUCCESS,
            output={"api_endpoints": ["https://example.com/api/list"]},
        ),
    )

    built = executor._build_input("signature_extractor", {"url": "https://example.com"})

    assert "1234567890abcdef" in built["js_code"]
    assert built["api_endpoints"] == ["https://example.com/api/list"]


def test_executor_bridges_flat_signature_fields_into_codegen_inputs():
    executor = ToolExecutor()
    executor.ctx.add_result(
        "signature_extractor",
        ToolResult(
            tool_name="signature_extractor",
            status=ToolStatus.SUCCESS,
            output={
                "key_value": "1234567890abcdef",
                "key_source": "hardcoded",
                "algorithm": "sha256",
                "confidence": 0.8,
                "param_format": "query_string",
            },
        ),
    )

    codegen_input = executor._build_input("codegen", {"goal": "reverse"})

    assert codegen_input["extracted_key"]["key_source"] == "hardcoded"
    assert codegen_input["signature_spec"]["algorithm_id"] == "sha256"


def test_executor_verify_prefers_generated_python_code_over_ambient_code_field():
    executor = ToolExecutor()
    executor.ctx.add_result(
        "codegen",
        ToolResult(
            tool_name="codegen",
            status=ToolStatus.SUCCESS,
            output={"python_code": "print('real crawler')\n", "js_code": ""},
        ),
    )

    built = executor._build_input("verify", {"code": "ignored"})

    assert built["code"] == "print('real crawler')\n"
    assert built["crawler_source"]["source"] == "codegen_output"
