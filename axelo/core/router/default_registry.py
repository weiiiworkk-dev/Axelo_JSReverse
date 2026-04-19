from __future__ import annotations

from axelo.core.router.registry import AgentRegistry
from axelo.agents.recon.agent import ReconAgent
from axelo.agents.browser.agent import BrowserAgent
from axelo.agents.analysis.agent import AnalysisAgent
from axelo.agents.codegen.agent import CodegenAgent
from axelo.agents.verification.agent import VerificationAgent
from axelo.agents.replay.agent import ReplayAgent
from axelo.agents.memory.agent import MemoryAgent


def build_default_registry() -> AgentRegistry:
    reg = AgentRegistry()
    for agent_cls in [ReconAgent, BrowserAgent, AnalysisAgent,
                      CodegenAgent, VerificationAgent, ReplayAgent, MemoryAgent]:
        reg.register(agent_cls())
    return reg
