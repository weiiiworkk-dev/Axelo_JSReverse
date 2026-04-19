from __future__ import annotations

import re
from typing import Any

import structlog

from axelo.core.base_agent import BaseAgent
from axelo.core.models.agent_result import AgentResult, ResultStatus
from axelo.core.models.task import SubTask

log = structlog.get_logger()

_ANTIBOT_SIGNATURES = {
    "cloudflare": [r"cf-ray", r"__cf_bm", r"_cfuvid", r"challenge-platform"],
    "akamai":     [r"_abck", r"bm_sz", r"akamai"],
    "datadome":   [r"datadome", r"dd_cookie"],
    "recaptcha":  [r"grecaptcha", r"recaptcha"],
    "incapsula":  [r"incap_ses", r"visid_incap"],
}


class ReconAgent(BaseAgent):
    name = "recon"

    async def execute(self, task: SubTask) -> AgentResult:
        url = self._extract_url(task.objective)
        log.info("recon_profiling", url=url)
        profile = await self._profile_site(url)
        return AgentResult(
            agent=self.name,
            status=ResultStatus.SUCCESS,
            data=profile,
        )

    async def _profile_site(self, url: str) -> dict[str, Any]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            headers_str = str(resp.headers).lower()
            body_str = resp.text[:5000].lower()
            combined = headers_str + body_str

            antibot = "none"
            for system, patterns in _ANTIBOT_SIGNATURES.items():
                if any(re.search(p, combined) for p in patterns):
                    antibot = system
                    break

            return {
                "url": url,
                "status_code": resp.status_code,
                "antibot_system": antibot,
                "js_challenge": resp.status_code in (403, 503) or "challenge" in combined,
                "difficulty": "hard" if antibot != "none" else "easy",
                "response_headers": dict(resp.headers),
            }
        except Exception as exc:
            log.warning("recon_http_error", error=str(exc))
            return {
                "url": url,
                "status_code": 0,
                "antibot_system": "unknown",
                "js_challenge": False,
                "difficulty": "unknown",
                "error": str(exc),
            }

    @staticmethod
    def _extract_url(objective: str) -> str:
        match = re.search(r"https?://\S+", objective)
        return match.group() if match else objective.strip()
