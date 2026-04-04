from __future__ import annotations


class RiskControlService:
    CHALLENGE_SIGNALS = ("x5secdata", "/_____tmd_____/punish")
    VALIDATION_SIGNALS = ("rgv587_error", "fail_sys_user_validate")

    def detect_text(self, *parts: str | None) -> str:
        signal_text = "\n".join(part for part in parts if part).lower()
        if not signal_text:
            return ""
        if any(signal in signal_text for signal in self.CHALLENGE_SIGNALS):
            return "risk-control challenge page detected"
        if any(signal in signal_text for signal in self.VALIDATION_SIGNALS):
            return "risk-control validation rejected the replay request"
        return ""

    def detect_replay(self, replay) -> str:
        return self.detect_text(getattr(replay, "response_body", ""), getattr(replay, "error", ""))
