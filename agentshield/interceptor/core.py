import json
import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentshield.modes.rollback import RollbackEngine
from agentshield.modes.simulator import ActionSimulator
from agentshield.modes.negotiator import AgentNegotiator, NegotiationResponse
from agentshield.policy.smart_scorer import SmartRiskScorer


@dataclass
class InterceptedAction:
    """One action that an agent tried to perform."""

    id: str = ""
    timestamp: str = ""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    agent_id: str = "default"
    risk_score: float = 0.0
    decision: str = "pending"
    mode: str = "shadow"
    result: Optional[Dict[str, Any]] = None
    rollback_plan: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentShield:
    def __init__(self, mode: str = "shadow", policy_path: str = None):
        self.mode = mode
        self.audit_log: List[InterceptedAction] = []
        self.policy_path = policy_path
        self._policy_engine = None
        self._simulator = ActionSimulator()
        self.rollback_engine = RollbackEngine()
        self._smart_scorer = SmartRiskScorer()
        if policy_path:
            from agentshield.policy.engine import PolicyEngine

            self._policy_engine = PolicyEngine(policy_path)
        self.negotiator = AgentNegotiator(self._policy_engine, risk_scorer=self._smart_scorer)

    async def intercept(
        self, tool_name: str, arguments: dict, agent_id: str = "default"
    ) -> InterceptedAction:
        action = InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            arguments=arguments or {},
            agent_id=agent_id,
            mode=self.mode,
        )
        simulation = self._simulator.simulate(
            action_id=action.id,
            tool_name=action.tool_name,
            arguments=action.arguments,
        )
        rollback_plan = self.rollback_engine.capture_state(
            action_id=action.id,
            tool_name=action.tool_name,
            original_state=action.arguments.get("original_state", {}),
            reversible=simulation.reversible,
        )
        policy_result = None

        if self._policy_engine:
            policy_result = await self._policy_engine.evaluate(action)
            action.decision = policy_result.decision
            action.risk_score = policy_result.risk_score
            action.result = {
                "policy_rule": policy_result.matched_rule,
            }
        else:
            self._score_risk(action)
            self._decide(action)
        self._prepare_preview(action)
        action.result = {
            **(action.result or {}),
            "simulation": asdict(simulation),
        }
        action.rollback_plan = rollback_plan.to_dict()
        self.audit_log.append(action)
        return action

    async def intercept_with_negotiation(
        self, tool_name: str, arguments: dict, agent_id: str = "default"
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        """Intercept + if blocked, automatically return negotiation guidance."""
        action = await self.intercept(tool_name, arguments, agent_id)
        if action.decision in ("block", "shadow"):
            negotiation = await self.negotiator.negotiate(action, None)
            return action, negotiation
        return action, None

    def intercept_with_negotiation_sync(
        self, tool_name: str, arguments: dict, agent_id: str = "default"
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        return asyncio.run(self.intercept_with_negotiation(tool_name, arguments, agent_id=agent_id))

    def intercept_sync(
        self, tool_name: str, arguments: dict, agent_id: str = "default"
    ) -> InterceptedAction:
        return asyncio.run(self.intercept(tool_name, arguments, agent_id=agent_id))

    def protect(self, tools: List[Any]) -> List[Any]:
        try:
            from agentshield.interceptor.langchain_hook import shield_all_tools

            return shield_all_tools(tools, self)
        except Exception:
            return tools

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.audit_log]

    def get_shadow_report(self) -> Dict[str, Any]:
        actions = self.audit_log
        by_tool: Dict[str, int] = {}
        by_decision: Dict[str, int] = {}
        risk_total = 0.0

        for action in actions:
            by_tool[action.tool_name] = by_tool.get(action.tool_name, 0) + 1
            by_decision[action.decision] = by_decision.get(action.decision, 0) + 1
            risk_total += action.risk_score

        total_actions = len(actions)
        avg_risk_score = (risk_total / total_actions) if total_actions else 0.0
        return {
            "total_actions": total_actions,
            "by_tool": by_tool,
            "by_decision": by_decision,
            "avg_risk_score": round(avg_risk_score, 4),
        }

    def save_audit_log(self, output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(self.get_audit_log(), handle, indent=2)

    def _score_risk(self, action: InterceptedAction) -> None:
        assessment = self._smart_scorer.score_action(
            tool_name=action.tool_name,
            arguments=action.arguments,
            agent_id=action.agent_id,
        )
        action.risk_score = assessment.score

    def _decide(self, action: InterceptedAction) -> None:
        if self.mode == "shadow":
            action.decision = "shadow"
            return
        if self.mode in {"dry-run", "dry_run"}:
            action.decision = "block"
            return
        if self.mode in {"approval", "approve"}:
            action.decision = "approve"
            return
        if self.mode in {"live", "enforce"}:
            action.decision = "allow"
            return

        action.decision = "pending"

    def _prepare_preview(self, action: InterceptedAction) -> None:
        action.result = {
            "status": action.decision,
            "message": f"{action.mode} preview for {action.tool_name}",
        }
        action.rollback_plan = {
            "strategy": "manual",
            "steps": [
                "Identify side effects for the action.",
                "Undo affected resources using tool-specific remediation.",
                "Verify final state matches expected baseline.",
            ],
        }
