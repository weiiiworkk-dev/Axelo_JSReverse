from __future__ import annotations

import json
from pathlib import Path

from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.models.target import TargetSite
from axelo.policies.runtime import RuntimePolicy


def write_run_report(
    output_path: Path,
    *,
    session_id: str,
    target: TargetSite,
    policy: RuntimePolicy,
    difficulty_level: str | None,
    verified: bool,
    completed: bool,
    total_cost_usd: float,
    total_tokens: int,
    ai_calls: int,
    browser_sessions: int,
    node_calls: int,
    route_label: str,
    reuse_hits: list[str],
    stage_costs: dict[str, dict],
    cost_strategy: str,
    analysis: AnalysisResult | None = None,
    generated: GeneratedCode | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "target": {
            "url": target.url,
            "goal": target.interaction_goal,
            "target_hint": target.target_hint,
            "use_case": target.use_case,
            "authorization_status": target.authorization_status,
            "replay_mode": target.replay_mode,
            "known_endpoint": target.known_endpoint,
            "antibot_type": target.antibot_type,
            "requires_login": target.requires_login,
            "output_format": target.output_format,
            "crawl_rate": target.crawl_rate,
        },
        "site_profile": target.site_profile.model_dump(mode="json"),
        "compliance": target.compliance.model_dump(mode="json"),
        "session_state": target.session_state.model_dump(mode="json"),
        "trace": target.trace.model_dump(mode="json"),
        "execution_plan": target.execution_plan.model_dump(mode="json") if target.execution_plan else None,
        "policy": policy.as_dict(),
        "result": {
            "difficulty_level": difficulty_level,
            "verified": verified,
            "completed": completed,
            "route_label": route_label,
            "analysis_ready_for_codegen": analysis.ready_for_codegen if analysis else None,
            "manual_review_required": analysis.manual_review_required if analysis else None,
            "signature_family": analysis.signature_family if analysis else "unknown",
            "analysis_notes": analysis.analysis_notes if analysis else "",
            "signature_spec": analysis.signature_spec.model_dump(mode="json") if analysis and analysis.signature_spec else None,
            "output_mode": generated.output_mode if generated else None,
            "crawler_script_path": str(generated.crawler_script_path) if generated and generated.crawler_script_path else None,
            "bridge_server_path": str(generated.bridge_server_path) if generated and generated.bridge_server_path else None,
            "manifest_path": str(generated.manifest_path) if generated and generated.manifest_path else None,
            "session_state_path": str(generated.session_state_path) if generated and generated.session_state_path else None,
            "verification_notes": generated.verification_notes if generated else "",
        },
        "cost": {
            "total_usd": round(total_cost_usd, 6),
            "total_tokens": total_tokens,
            "ai_calls": ai_calls,
            "browser_sessions": browser_sessions,
            "node_calls": node_calls,
            "route_label": route_label,
            "reuse_hits": reuse_hits,
            "cost_strategy": cost_strategy,
            "stage_costs": stage_costs,
            "stage_durations": {stage: metrics.get("duration_ms", 0) for stage, metrics in stage_costs.items()},
            "stage_exit_reason": {stage: metrics.get("exit_reason", "") for stage, metrics in stage_costs.items()},
        },
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
