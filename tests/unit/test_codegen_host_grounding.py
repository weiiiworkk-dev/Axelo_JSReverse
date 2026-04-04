from __future__ import annotations

from axelo.agents.codegen_agent import (
    _preferred_api_base,
    _repair_generated_code_for_target,
    _render_base_crawler_template,
)
from axelo.agents.codegen_services import _safe_default_headers
from axelo.models.analysis import AIHypothesis
from axelo.models.target import RequestCapture, TargetSite


def _make_target() -> TargetSite:
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="sess-1",
        interaction_goal="商品价格抓取",
        target_hint="iphone 15",
    )
    target.target_requests = [
        RequestCapture(
            url="https://acs-m.lazada.com.my/h5/mtop.relationrecommend.lazadarecommend.recommend/1.0/",
            method="GET",
        )
    ]
    return target


def test_preferred_api_base_uses_observed_h5_host():
    target = _make_target()

    assert _preferred_api_base(target) == "https://acs-m.lazada.com.my/h5"


def test_repair_generated_code_rewrites_wrong_host_and_cookie_domain():
    target = _make_target()
    code = """
MTOP_BASE_URL = "https://h5api.m.lazada.com/h5"
SEED_URL = "https://www.lazada.com/"
COOKIE_DOMAIN = ".lazada.com"
fallback = "https://acs-m.lazada.com/h5"
"""

    repaired = _repair_generated_code_for_target(code, target)

    assert 'MTOP_BASE_URL = "https://acs-m.lazada.com.my/h5"' in repaired
    assert 'SEED_URL = "https://www.lazada.com.my/"' in repaired
    assert 'COOKIE_DOMAIN = ".lazada.com.my"' in repaired
    assert 'fallback = "https://acs-m.lazada.com.my/h5"' in repaired


def test_render_base_crawler_template_uses_python_literals_for_runtime_dicts():
    target = _make_target()
    rendered = _render_base_crawler_template(
        target,
        hypothesis=AIHypothesis(
            algorithm_description="Use bridge",
            codegen_strategy="js_bridge",
        ),
        dynamic=None,
        bridge_port=8721,
    )

    assert "DEFAULT_ENVIRONMENT = {'enabled': True" in rendered
    assert "DEFAULT_INTERACTION = {'enabled': True" in rendered
    assert "'dischargingTime': None" in rendered


def test_safe_default_headers_only_include_origin_when_observed():
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="sess-2",
        interaction_goal="搜索结果抓取",
        target_hint="iphone 15",
        target_requests=[
            RequestCapture(
                url="https://www.lazada.com.my/catalog/?ajax=true&page=1&q=iphone%2015",
                method="GET",
                request_headers={
                    "accept": "application/json, text/plain, */*",
                    "x-csrf-token": "abc123",
                },
            )
        ],
    )

    headers = _safe_default_headers(target)

    assert headers["x-csrf-token"] == "abc123"
    assert "Origin" not in headers


def test_rendered_bridge_crawler_avoids_forcing_origin_for_catalog_request():
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="sess-3",
        interaction_goal="搜索结果抓取",
        target_hint="iphone 15",
        target_requests=[
            RequestCapture(
                url="https://www.lazada.com.my/catalog/?ajax=true&page=1&q=iphone%2015",
                method="GET",
                request_headers={
                    "accept": "application/json, text/plain, */*",
                    "x-csrf-token": "abc123",
                },
            )
        ],
    )

    rendered = _render_base_crawler_template(
        target,
        hypothesis=AIHypothesis(
            algorithm_description="Use bridge",
            codegen_strategy="js_bridge",
        ),
        dynamic=None,
        bridge_port=8721,
    )

    assert "'x-csrf-token': 'abc123'" in rendered
    assert "'Origin':" not in rendered
    assert "self._cookies and self._should_attach_cookie_header(final_url, method, headers)" in rendered
