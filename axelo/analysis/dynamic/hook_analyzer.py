from __future__ import annotations
from axelo.models.analysis import HookIntercept, StaticAnalysis


# 高价值 Hook（强烈暗示签名生成）
HIGH_VALUE_APIS = {
    "crypto.subtle.sign",
    "crypto.subtle.digest",
    "crypto.subtle.encrypt",
    "crypto.getRandomValues",
    "window.btoa",
}


class HookAnalyzer:
    """
    分析 Hook 拦截记录，推断：
    - 哪些 API 被实际调用（过滤掉未触发的）
    - 调用顺序与重复次数
    - 与静态分析 TokenCandidate 的关联
    """

    def analyze(
        self,
        intercepts: list[HookIntercept],
        static: StaticAnalysis | None = None,
    ) -> dict:
        if not intercepts:
            return {"apis_called": [], "high_value": [], "field_mapping": {}, "summary": "无 Hook 触发"}

        # 统计各 API 调用次数
        api_counts: dict[str, int] = {}
        for ic in intercepts:
            api_counts[ic.api_name] = api_counts.get(ic.api_name, 0) + 1

        apis_called = sorted(api_counts.keys(), key=lambda k: -api_counts[k])
        high_value = [a for a in apis_called if a in HIGH_VALUE_APIS]

        # 尝试将 Hook 输出与目标请求字段关联
        field_mapping: dict[str, str] = {}
        if static:
            for candidate in static.token_candidates:
                for ic in intercepts:
                    if candidate.request_field and _apis_related(ic.api_name, candidate.token_type):
                        field_mapping[ic.api_name] = candidate.request_field

        summary_parts = [f"{api}×{cnt}" for api, cnt in api_counts.items()]
        summary = "Hook调用: " + ", ".join(summary_parts[:8])

        return {
            "apis_called": apis_called,
            "high_value": high_value,
            "api_counts": api_counts,
            "field_mapping": field_mapping,
            "summary": summary,
        }


def _apis_related(api_name: str, token_type: str) -> bool:
    mapping = {
        "hmac": ["crypto.subtle.sign"],
        "sha256": ["crypto.subtle.digest"],
        "aes": ["crypto.subtle.encrypt", "crypto.subtle.decrypt"],
        "base64": ["window.btoa", "window.atob"],
    }
    return api_name in mapping.get(token_type, [])
