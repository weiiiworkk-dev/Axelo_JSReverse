from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisRouteDecision:
    route: str
    requires_ai: bool
    use_template_codegen: bool = False


class AnalysisRoutingService:
    def should_run_dynamic(self, ctx) -> bool:
        if ctx.difficulty is None or ctx.target.execution_plan is None:
            return False
        if ctx.difficulty.recommended_path not in ("static+dynamic", "full+human"):
            return False
        return ctx.governor.allow_dynamic(ctx.cost, ctx.target.execution_plan)

    def choose_route(self, ctx) -> AnalysisRouteDecision:
        if self.should_use_static_only(ctx):
            return AnalysisRouteDecision(route="static_only", requires_ai=False)
        if self.should_use_template_codegen(ctx):
            return AnalysisRouteDecision(route="template_codegen", requires_ai=False, use_template_codegen=True)
        if self.should_use_family_codegen(ctx):
            return AnalysisRouteDecision(route="family_codegen", requires_ai=False)
        if ctx.target.execution_plan and ctx.target.execution_plan.ai_mode == "scanner_only":
            return AnalysisRouteDecision(route="scanner_only", requires_ai=True)
        return AnalysisRouteDecision(route="full_ai", requires_ai=True)

    def should_use_static_only(self, ctx) -> bool:
        plan = ctx.target.execution_plan
        if plan is None or not plan.skip_codegen:
            return False
        if ctx.analysis_cache_hit:
            return True
        if ctx.memory_ctx.get("known_pattern"):
            return True
        return self.top_static_confidence(ctx.static_results) >= 0.75

    def should_use_template_codegen(self, ctx) -> bool:
        if ctx.family_match is None or ctx.target.execution_plan is None:
            return False
        return bool(
            getattr(ctx.family_match, "template_ready", False)
            and not ctx.target.execution_plan.skip_codegen
            and getattr(ctx.family_match, "confidence", 0.0) >= 0.8
            and self._template_matches_observed_request(ctx)
        )

    def should_use_family_codegen(self, ctx) -> bool:
        if ctx.family_match is None or ctx.target.execution_plan is None:
            return False
        return bool(
            not ctx.target.execution_plan.skip_codegen
            and not getattr(ctx.family_match, "template_ready", False)
            and getattr(ctx.family_match, "codegen_strategy", "") == "js_bridge"
            and getattr(ctx.family_match, "confidence", 0.0) >= 0.8
        )

    def requires_low_confidence_confirmation(self, ctx) -> bool:
        return bool(
            ctx.analysis is not None
            and not ctx.analysis.ready_for_codegen
            and ctx.mode_name != "auto"
        )

    def has_static_candidates(self, static_results) -> bool:
        return any(analysis.token_candidates for analysis in static_results.values())

    def top_static_confidence(self, static_results) -> float:
        best = 0.0
        for analysis in static_results.values():
            for candidate in analysis.token_candidates:
                best = max(best, candidate.confidence)
        return best

    def _template_matches_observed_request(self, ctx) -> bool:
        expected = {
            str(key).lower()
            for key in getattr(ctx.family_match, "outputs", {}).keys()
            if key
        }
        observed = set()
        requests = getattr(ctx.target, "target_requests", None) or getattr(ctx.target, "captured_requests", None) or []
        if not requests:
            return True
        if not expected:
            return False
        for request in requests[:5]:
            for key in (request.request_headers or {}).keys():
                observed.add(str(key).lower())

            url = (request.url or "").lower()
            if "?" in url:
                query = url.split("?", 1)[1]
                for item in query.split("&"):
                    if item:
                        observed.add(item.split("=", 1)[0].lower())

            body = request.request_body
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="ignore")
            if isinstance(body, str):
                for item in body.split("&"):
                    if "=" in item:
                        observed.add(item.split("=", 1)[0].strip().lower())

        alias_groups = [
            {"sign", "x-sign", "signature"},
            {"t", "ts", "timestamp", "x-timestamp"},
            {"nonce", "x-nonce"},
            {"token", "x-token", "authorization", "accesstoken", "access_token"},
        ]
        for expected_key in expected:
            if expected_key in observed:
                continue
            if any(expected_key in group and observed.intersection(group) for group in alias_groups):
                continue
            return False
        return True
