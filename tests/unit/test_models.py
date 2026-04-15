"""Core data model tests."""

from axelo.browser.profiles import PROFILES
from axelo.models.analysis import AIHypothesis, TokenCandidate
from axelo.models.target import BrowserProfile, RequestCapture, TargetSite


class TestRequestCapture:
    def test_basic_capture(self):
        cap = RequestCapture(
            url="https://api.example.com/search",
            method="POST",
            request_headers={"X-Sign": "abc123", "Content-Type": "application/json"},
            response_status=200,
        )
        assert cap.url == "https://api.example.com/search"
        assert cap.method == "POST"
        assert cap.response_status == 200

    def test_token_fields_default_empty(self):
        cap = RequestCapture(url="https://x.com", method="GET")
        assert cap.token_fields == []

    def test_binary_body_serializes_without_utf8_failure(self):
        cap = RequestCapture(
            url="https://api.example.com/data",
            method="POST",
            request_body=b"\x80\x81\x82payload",
            response_body=b"\x00\x01\x02binary",
        )
        target = TargetSite(
            url="https://example.com",
            session_id="AAA-000001",
            interaction_goal="demo",
            captured_requests=[cap],
            target_requests=[cap],
        )
        payload = target.model_dump(mode="json")
        assert isinstance(payload["captured_requests"][0]["request_body"], str)
        assert isinstance(payload["captured_requests"][0]["response_body"], str)
        assert target.model_dump_json()


class TestBrowserProfile:
    def test_environment_simulation_defaults(self):
        profile = BrowserProfile()
        assert profile.environment_simulation.profile_name == "desktop"
        assert profile.interaction_simulation.mode == "playwright_mouse"
        assert profile.environment_simulation.webgl.minimum_parameters["MAX_TEXTURE_SIZE"] == 16384

    def test_mobile_profile_uses_mobile_simulation(self):
        profile = PROFILES["mobile"]
        assert profile.environment_simulation.is_mobile is True
        assert profile.environment_simulation.has_touch is True
        assert profile.environment_simulation.media.pointer == "coarse"

    def test_unknown_stealth_field_is_ignored(self):
        profile = BrowserProfile.model_validate({"stealth": True})
        assert profile.environment_simulation.profile_name == "desktop"


class TestTokenCandidate:
    def test_candidate_creation(self):
        candidate = TokenCandidate(
            func_id="bundle01:signRequest",
            token_type="hmac",
            confidence=0.85,
            evidence=["contains hmac marker", "function name includes sign"],
            request_field="X-Sign",
        )
        assert candidate.confidence == 0.85
        assert candidate.token_type == "hmac"

    def test_confidence_bounds(self):
        candidate = TokenCandidate(func_id="x:y", token_type="md5", confidence=0.0)
        assert 0.0 <= candidate.confidence <= 1.0


class TestAIHypothesis:
    def test_hypothesis_defaults(self):
        hypothesis = AIHypothesis(
            algorithm_description="HMAC-SHA256 with timestamp",
            codegen_strategy="python_reconstruct",
            python_feasibility=0.9,
            confidence=0.85,
        )
        assert hypothesis.steps == []
        assert hypothesis.inputs == []
        assert hypothesis.outputs == {}

    def test_codegen_strategy_values(self):
        for strategy in ("python_reconstruct", "js_bridge", "observed_replay"):
            hypothesis = AIHypothesis(
                algorithm_description="test",
                codegen_strategy=strategy,
            )
            assert hypothesis.codegen_strategy == strategy
