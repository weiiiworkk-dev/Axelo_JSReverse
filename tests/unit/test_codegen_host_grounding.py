from __future__ import annotations

from axelo.agents.codegen_agent import _preferred_api_base, _repair_generated_code_for_target
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
