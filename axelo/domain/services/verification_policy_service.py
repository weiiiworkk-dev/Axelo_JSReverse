from __future__ import annotations


class VerificationPolicyService:
    def stability_runs(self, ctx) -> int:
        return ctx.governor.stability_runs(ctx.target, ctx.target.execution_plan)

    def max_verify_retries(self, ctx) -> int:
        return max(1, ctx.target.compliance.max_auto_verify_retries)

    def live_verify(self, target, live_verify: bool | None = None) -> bool:
        if live_verify is None:
            return target.compliance.allow_live_verification
        return live_verify
