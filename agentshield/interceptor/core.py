import json
import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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
        if policy_path:
            from agentshield.policy.engine import PolicyEngine

            self._policy_engine = PolicyEngine(policy_path)

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

        if self._policy_engine:
            policy_result = await self._policy_engine.evaluate(action)
            action.decision = policy_result.decision
            action.risk_score = policy_result.risk_score
        else:
            self._score_risk(action)
            self._decide(action)
        self._prepare_preview(action)
        self.audit_log.append(action)
        return action

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
        """Basic heuristic until policy engine scoring is wired in."""
        if self._policy_engine and hasattr(self._policy_engine, "score"):
            action.risk_score = float(
                self._policy_engine.score(
                    tool_name=action.tool_name,
                    arguments=action.arguments,
                    agent_id=action.agent_id,
                )
            )
            return

        risky_keywords = {"delete", "drop", "remove", "revoke", "terminate", "write"}
        if any(keyword in action.tool_name.lower() for keyword in risky_keywords):
            action.risk_score = 0.8
        else:
            action.risk_score = 0.2

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
