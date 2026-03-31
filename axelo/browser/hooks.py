from __future__ import annotations
import json
import time
from playwright.async_api import Page
from axelo.models.analysis import HookIntercept
import structlog

log = structlog.get_logger()

# 默认 Hook 目标列表（与 execute_hook.mjs 中的 buildHookCode 共用此格式）
DEFAULT_HOOK_TARGETS: list[str] = [
    # 加密相关
    "crypto.subtle.sign",
    "crypto.subtle.digest",
    "crypto.subtle.encrypt",
    "crypto.subtle.decrypt",
    "crypto.getRandomValues",
    # 编码
    "window.btoa",
    "window.atob",
    # 时间
    "Date.now",
    # 存储
    "localStorage.getItem",
    "localStorage.setItem",
    "sessionStorage.getItem",
    # 网络（在 Playwright 拦截中更好处理，这里作为补充）
    "XMLHttpRequest.prototype.open",
    "XMLHttpRequest.prototype.setRequestHeader",
]


class JSHookInjector:
    """
    通过 CDP Page.addScriptToEvaluateOnNewDocument 注入 Hook 脚本。
    使用 CDP Runtime binding 将拦截结果回传到 Python。
    """

    def __init__(self) -> None:
        self.intercepts: list[HookIntercept] = []
        self._sequence = 0

    async def inject(self, page: Page, targets: list[str] | None = None) -> None:
        if targets is None:
            targets = DEFAULT_HOOK_TARGETS

        hook_js = self._build_hook_js(targets)

        # 注册 CDP binding，拦截数据通过此 binding 回传
        await page.expose_binding(
            "__axelo_hook_cb",
            self._on_hook_fired,
            handle=False,
        )

        # 在每次导航后自动注入（包括首次）
        await page.add_init_script(hook_js)
        log.info("hooks_injected", count=len(targets))

    def _on_hook_fired(self, source: dict, api_name: str, args_json: str, return_json: str, stack_json: str) -> None:
        try:
            stack = json.loads(stack_json) if stack_json else []
        except Exception:
            stack = []

        intercept = HookIntercept(
            api_name=api_name,
            args_repr=args_json or "[]",
            return_repr=return_json or "null",
            stack_trace=stack,
            timestamp=time.time(),
            sequence=self._sequence,
        )
        self._sequence += 1
        self.intercepts.append(intercept)
        log.debug("hook_fired", api=api_name, seq=intercept.sequence)

    def _build_hook_js(self, targets: list[str]) -> str:
        """生成在浏览器中运行的 Hook 注入脚本"""
        lines = [
            "(function() {",
            "  function __hook(api, orig, ctx) {",
            "    return function(...args) {",
            "      let ret;",
            "      try { ret = orig.apply(ctx || this, args); } catch(e) { throw e; }",
            "      try {",
            "        const argsJson = JSON.stringify(args, __safeReplacer);",
            "        const retJson = JSON.stringify(ret, __safeReplacer);",
            "        const stack = new Error().stack.split('\\n').slice(2, 6);",
            "        window.__axelo_hook_cb(api, argsJson, retJson, JSON.stringify(stack));",
            "      } catch(_) {}",
            "      return ret;",
            "    };",
            "  }",
            "  function __safeReplacer(k, v) {",
            "    if (v instanceof ArrayBuffer) return {__type:'ArrayBuffer',hex:Array.from(new Uint8Array(v)).map(b=>b.toString(16).padStart(2,'0')).join('')};",
            "    if (v instanceof Uint8Array) return {__type:'Uint8Array',hex:Array.from(v).map(b=>b.toString(16).padStart(2,'0')).join('')};",
            "    if (v instanceof Promise) return '[Promise]';",
            "    if (typeof v === 'function') return '[Function]';",
            "    return v;",
            "  }",
        ]

        for target in targets:
            parts = target.split(".")
            if len(parts) < 2:
                continue
            obj_expr = ".".join(parts[:-1])
            method = parts[-1]
            lines += [
                f"  try {{",
                f"    if (typeof {obj_expr} !== 'undefined' && typeof {obj_expr}.{method} === 'function') {{",
                f"      const _orig = {obj_expr}.{method};",
                f"      {obj_expr}.{method} = __hook({json.dumps(target)}, _orig, {obj_expr});",
                f"    }}",
                f"  }} catch(_) {{}}",
            ]

        lines.append("})();")
        return "\n".join(lines)

    def get_intercepts(self) -> list[HookIntercept]:
        return list(self.intercepts)

    def clear(self) -> None:
        self.intercepts.clear()
        self._sequence = 0
