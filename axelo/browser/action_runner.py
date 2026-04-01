from __future__ import annotations

from pydantic import BaseModel, Field
from playwright.async_api import Page

from axelo.models.site_profile import BrowserAction, BrowserActionType
from axelo.models.target import TargetSite
from axelo.policies.runtime import RuntimePolicy


class ActionRunResult(BaseModel):
    executed: int = 0
    failures: list[str] = Field(default_factory=list)
    final_url: str = ""


def default_action_flow(target: TargetSite, policy: RuntimePolicy) -> list[BrowserAction]:
    if target.execution_plan and not target.execution_plan.enable_action_flow:
        actions: list[BrowserAction] = []
    else:
        actions = list(target.site_profile.action_flow)
    if actions:
        return actions
    return [
        BrowserAction(
            action_type=BrowserActionType.NAVIGATE,
            url=target.url,
            description="Navigate to target URL",
        ),
        BrowserAction(
            action_type=BrowserActionType.WAIT,
            duration_ms=policy.post_navigation_wait_ms,
            description="Wait for initial network activity to settle",
        ),
    ]


class ActionRunner:
    async def run(
        self,
        page: Page,
        target: TargetSite,
        policy: RuntimePolicy,
    ) -> ActionRunResult:
        result = ActionRunResult(final_url=page.url)
        for action in default_action_flow(target, policy):
            try:
                await self._execute(page, action, policy)
                result.executed += 1
                result.final_url = page.url
            except Exception as exc:
                message = f"{action.action_type.value}: {exc}"
                result.failures.append(message)
                if not action.optional:
                    raise
        return result

    async def _execute(self, page: Page, action: BrowserAction, policy: RuntimePolicy) -> None:
        if action.action_type == BrowserActionType.NAVIGATE:
            await page.goto(action.url or page.url, wait_until=policy.goto_wait_until, timeout=30_000)
            return
        if action.action_type == BrowserActionType.WAIT:
            await page.wait_for_timeout(action.duration_ms or policy.post_navigation_wait_ms)
            return
        if action.action_type == BrowserActionType.CLICK:
            await page.locator(action.selector).first.click(timeout=10_000)
            return
        if action.action_type == BrowserActionType.TYPE:
            await page.locator(action.selector).first.fill(action.text, timeout=10_000)
            return
        if action.action_type == BrowserActionType.PRESS:
            await page.locator(action.selector).first.press(action.key or "Enter", timeout=10_000)
            return
        if action.action_type == BrowserActionType.SCREENSHOT:
            await page.screenshot(path=action.url or action.text or "action-shot.png")
            return
        if action.action_type == BrowserActionType.EVALUATE:
            await page.evaluate(action.script)
            return
        raise ValueError(f"Unsupported action type: {action.action_type}")
