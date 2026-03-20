from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class Agent:
    id: str
    name: str
    owner: str
    allowed_tools: list
    max_risk_tolerance: float
    reputation_score: float
    total_actions: int
    blocked_actions: int
    created_at: str
    status: str
    role: str | None = None

    def to_dict(self) -> Dict:
        return asdict(self)


class AgentRegistry:
    """Track all agents, their permissions, reputation scores, and lifecycle."""

    def __init__(self):
        self._agents: Dict[str, Agent] = {}

    def register_agent(
        self,
        agent_id,
        name,
        owner,
        allowed_tools,
        max_risk_tolerance,
        role: str | None = None,
    ) -> Agent:
        agent = Agent(
            id=agent_id,
            name=name,
            owner=owner,
            allowed_tools=list(allowed_tools),
            max_risk_tolerance=float(max_risk_tolerance),
            role=role,
            reputation_score=0.5,
            total_actions=0,
            blocked_actions=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )
        self._agents[agent_id] = agent
        return agent

    def get_agent(self, agent_id) -> Agent:
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")
        return self._agents[agent_id]

    def update_reputation(self, agent_id, action_outcome):
        agent = self.get_agent(agent_id)
        agent.total_actions += 1
        if action_outcome == "block":
            agent.blocked_actions += 1
            agent.reputation_score = max(0.0, round(agent.reputation_score - 0.05, 4))
        else:
            agent.reputation_score = min(1.0, round(agent.reputation_score + 0.01, 4))
        if agent.reputation_score < 0.2:
            agent.status = "suspended"

    def list_agents(self) -> List[dict]:
        return [agent.to_dict() for agent in self._agents.values()]

    def deactivate_agent(self, agent_id):
        agent = self.get_agent(agent_id)
        agent.status = "deactivated"
