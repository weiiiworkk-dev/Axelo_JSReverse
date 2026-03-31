from __future__ import annotations
from axelo.models.analysis import HookIntercept, DynamicAnalysis
from axelo.models.target import RequestCapture


class TraceBuilder:
    """
    将 Hook 拦截序列与网络请求时序关联，
    重建"哪些加密调用发生在目标请求之前"的因果链。
    """

    def build(
        self,
        bundle_id: str,
        intercepts: list[HookIntercept],
        target_requests: list[RequestCapture],
        hook_analysis: dict,
    ) -> DynamicAnalysis:
        if not intercepts or not target_requests:
            return DynamicAnalysis(bundle_id=bundle_id)

        # 找到第一个目标请求的时间戳
        first_target_ts = min(r.timestamp for r in target_requests if r.timestamp > 0)

        # 收集在目标请求发出前的 Hook 调用（窗口：最多5秒前）
        pre_request_intercepts = [
            ic for ic in intercepts
            if 0 < ic.timestamp <= first_target_ts
            and (first_target_ts - ic.timestamp) <= 5.0
        ]

        # 确认的生成器：出现在目标请求前的高价值 API 对应的函数
        from axelo.analysis.dynamic.hook_analyzer import HIGH_VALUE_APIS
        confirmed_generators: list[str] = []
        crypto_primitives: list[str] = []

        for ic in pre_request_intercepts:
            if ic.api_name in HIGH_VALUE_APIS:
                crypto_primitives.append(ic.api_name)
                # 从调用栈推断函数名
                for frame in ic.stack_trace:
                    if frame and "axelo" not in frame.lower():
                        confirmed_generators.append(frame.strip())
                        break

        # 去重
        confirmed_generators = list(dict.fromkeys(confirmed_generators))
        crypto_primitives = list(dict.fromkeys(crypto_primitives))

        return DynamicAnalysis(
            bundle_id=bundle_id,
            hook_intercepts=pre_request_intercepts,
            confirmed_generators=confirmed_generators,
            field_mapping=hook_analysis.get("field_mapping", {}),
            crypto_primitives=crypto_primitives,
        )
