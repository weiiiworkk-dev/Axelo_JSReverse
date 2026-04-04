from __future__ import annotations

from axelo.analysis.family_detector import detect_signature_family
from axelo.models.analysis import StaticAnalysis, TokenCandidate
from axelo.models.target import RequestCapture, TargetSite


def test_detect_signature_family_handles_secret_candidate_regex_with_known_pattern():
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="fam01",
        interaction_goal="collect search results",
    )
    static_results = {
        "bundle": StaticAnalysis(
            bundle_id="bundle",
            crypto_imports=["hmac", "sha256"],
            string_constants=[
                "abcDEF123_-+=xyz",
                "short",
            ],
            token_candidates=[
                TokenCandidate(
                    func_id="bundle:sign",
                    token_type="hmac",
                    confidence=0.91,
                    request_field="X-Sign",
                )
            ],
        )
    }

    match = detect_signature_family(
        target,
        static_results,
        memory_ctx={
            "known_pattern": {
                "algorithm_type": "hmac",
            }
        },
        templates=[],
    )

    assert match.family_id == "hmac-sha256-timestamp"
    assert match.algorithm_type == "hmac"
    assert match.secret_candidate == "abcDEF123_-+=xyz"


def test_detect_signature_family_prefers_mtop_bridge_for_observed_h5_requests():
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="fam02",
        interaction_goal="collect search results",
    )
    target.target_requests = [
        RequestCapture(
            url=(
                "https://acs-m.lazada.com.my/h5/mtop.relationrecommend.lazadarecommend.recommend/1.0/"
                "?appKey=24677475&t=123&sign=abc&data=%7B%7D"
            ),
            method="GET",
        )
    ]

    match = detect_signature_family(
        target,
        {"bundle": StaticAnalysis(bundle_id="bundle")},
        memory_ctx={},
        templates=[],
    )

    assert match.family_id == "mtop-h5-token"
    assert match.algorithm_type == "mtop"
    assert match.codegen_strategy == "js_bridge"
    assert match.template_ready is False


def test_detect_signature_family_ignores_unverified_memory_pattern_for_runtime_choice():
    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="fam03",
        interaction_goal="collect search results",
    )
    target.target_requests = [
        RequestCapture(
            url="https://acs-m.lazada.com.my/h5/mtop.demo/1.0/?appKey=24677475&t=123&sign=abc&data=%7B%7D",
            method="GET",
        )
    ]

    match = detect_signature_family(
        target,
        {"bundle": StaticAnalysis(bundle_id="bundle")},
        memory_ctx={
            "known_pattern": {
                "algorithm_type": "custom",
                "verified": False,
                "success_count": 0,
            }
        },
        templates=[],
    )

    assert match.family_id == "mtop-h5-token"
