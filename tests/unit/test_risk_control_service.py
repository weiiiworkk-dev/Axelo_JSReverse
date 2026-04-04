from __future__ import annotations

from axelo.domain.services import RiskControlService
from axelo.verification.replayer import ReplayResult


def test_detect_text_flags_challenge_pages():
    service = RiskControlService()

    assert service.detect_text("https://www.lazada.com.my/_____tmd_____/punish?x5secdata=abc") == (
        "risk-control challenge page detected"
    )


def test_detect_replay_flags_validation_failures():
    service = RiskControlService()
    replay = ReplayResult(
        ok=False,
        status_code=200,
        response_body='{"ret":["FAIL_SYS_USER_VALIDATE","RGV587_ERROR"]}',
    )

    assert service.detect_replay(replay) == "risk-control validation rejected the replay request"
