# axelo/core/router/registry.py
from __future__ import annotations

from axelo.core.base_agent import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        if name not in self._agents:
            raise KeyError(f"Agent {name!r} not registered. Available: {list(self._agents)}")
        return self._agents[name]

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())
