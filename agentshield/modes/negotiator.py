from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NegotiationResponse:
    action_id: str
    status: str
    explanation: Dict[str, Any]
    suggestions: List[Dict[str, Any]]
    proposed_safe_action: Dict[str, Any]
    escalation_available: bool
    retry_endpoint: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NegotiationRecord:
    action_id: str
    agent_id: str
    decision: str
    explanation: Dict[str, Any]
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    proposed_safe_action: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentNegotiator:
    """
    When an agent's action is blocked, this provides:
    1. Clear explanation of WHY it was blocked
    2. Which policy rule triggered it
    3. Specific suggestions to make the action acceptable
    4. A way for the agent to resubmit a modified action
    """

    def __init__(self, policy_engine, risk_scorer=None):
        self.policy = policy_engine
        self.risk_scorer = risk_scorer
        self.negotiation_history: List[NegotiationRecord] = []

    async def negotiate(self, action, policy_result=None) -> NegotiationResponse:
        """
        Called when an action is blocked/shadowed.
        Returns explanation + suggestions.
        """
        explanation = self._build_explanation(action, policy_result)
        suggestions = self._build_suggestions(action, policy_result)
        safe_version = self._propose_safe_version(action)

        response = NegotiationResponse(
            action_id=action.id,
            status="negotiating",
            explanation=explanation,
            suggestions=suggestions,
            proposed_safe_action=safe_version,
            escalation_available=True,
            retry_endpoint=f"/api/v1/retry/{action.id}",
        )
        self.negotiation_history.append(
            NegotiationRecord(
                action_id=action.id,
                agent_id=action.agent_id,
                decision=action.decision,
                explanation=explanation,
                suggestions=suggestions,
                proposed_safe_action=safe_version,
            )
        )
        return response

    def get_history(self) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in self.negotiation_history]

    def _build_explanation(self, action, policy_result) -> Dict[str, Any]:
        human = self._generate_human_explanation(action, policy_result)
        reason = ""
        if policy_result is not None and getattr(policy_result, "matched_rule", ""):
            reason = policy_result.matched_rule
        else:
            reason = (action.result or {}).get("policy_rule", "default policy")
        return {
            "decision": action.decision,
            "reason": reason or "default policy",
            "risk_score": action.risk_score,
            "risk_factors": self._identify_risk_factors(action),
            "human_readable": human,
        }

    def _identify_risk_factors(self, action) -> List[Dict[str, Any]]:
        factors: List[Dict[str, Any]] = []
        args = action.arguments

        for field_name in ["to", "recipient", "email", "channel"]:
            value = str(args.get(field_name, ""))
            if value and "@" in value and "@yourcompany.com" not in value:
                factors.append(
                    {"type": "external_recipient", "value": value, "severity": "high"}
                )

        destructive = ["delete", "drop", "remove", "destroy", "purge", "truncate", "kill", "terminate"]
        content = str(args).lower()
        for word in destructive:
            if word in content:
                factors.append(
                    {"type": "destructive_keyword", "value": word, "severity": "critical"}
                )

        sensitive = ["password", "secret", "token", "key", "credential", "ssn", "credit_card"]
        for word in sensitive:
            if word in content:
                factors.append({"type": "sensitive_data", "value": word, "severity": "critical"})

        if args.get("channel") in ["#general", "#all-hands", "#everyone"]:
            factors.append(
                {"type": "wide_broadcast", "value": args["channel"], "severity": "medium"}
            )

        if isinstance(args.get("ids"), list) and len(args["ids"]) > 10:
            factors.append(
                {
                    "type": "bulk_operation",
                    "count": len(args["ids"]),
                    "severity": "high",
                }
            )
        return factors

    def _build_suggestions(self, action, policy_result) -> List[Dict[str, Any]]:
        _ = policy_result
        suggestions: List[Dict[str, Any]] = []
        factors = self._identify_risk_factors(action)
        for factor in factors:
            if factor["type"] == "external_recipient":
                suggestions.append(
                    {
                        "action": "modify_recipient",
                        "description": f"Route through internal relay instead of sending directly to {factor['value']}",
                        "example_modification": {"to": "relay@yourcompany.com", "original_to": factor["value"]},
                    }
                )
            elif factor["type"] == "destructive_keyword":
                suggestions.append(
                    {
                        "action": "use_safe_alternative",
                        "description": f"Replace '{factor['value']}' with a non-destructive alternative (archive, disable, soft-delete)",
                    }
                )
            elif factor["type"] == "wide_broadcast":
                suggestions.append(
                    {
                        "action": "narrow_scope",
                        "description": f"Send to a targeted channel instead of {factor['value']}",
                    }
                )
            elif factor["type"] == "bulk_operation":
                suggestions.append(
                    {
                        "action": "batch_with_confirmation",
                        "description": f"Process {factor['count']} items in smaller batches with confirmation between each",
                    }
                )

        suggestions.append(
            {
                "action": "request_human_approval",
                "description": "Escalate to a human reviewer who can override this decision",
                "endpoint": "/api/v1/request-approval",
            }
        )
        return suggestions

    def _generate_human_explanation(self, action, policy_result) -> str:
        factors = self._identify_risk_factors(action)
        external = next((f for f in factors if f.get("type") == "external_recipient"), None)
        factor_text = ", ".join(f"{f['type']} ({f['severity']})" for f in factors) or "no explicit factors"
        rule = (
            getattr(policy_result, "matched_rule", None)
            or (action.result or {}).get("policy_rule")
            or "default policy"
        )
        prefix = ""
        if external is not None:
            prefix = f"External recipient detected ({external.get('value')}). "
        return (
            f"{prefix}Action '{action.tool_name}' was marked '{action.decision}' by policy '{rule}'. "
            f"Risk score: {action.risk_score}. Risk factors: {factor_text}."
        )

    def _propose_safe_version(self, action) -> Dict[str, Any]:
        safe_args = dict(action.arguments)
        if action.tool_name in ("send_email", "gmail_send"):
            to = safe_args.get("to", "")
            if to and "@yourcompany.com" not in str(to):
                safe_args["cc"] = "manager@yourcompany.com"
                safe_args["_agentshield_note"] = "Added manager CC for external send"

        if "delete" in str(safe_args).lower():
            safe_args["_agentshield_suggestion"] = "Consider using 'archive' instead of 'delete'"

        return {
            "tool_name": action.tool_name,
            "modified_arguments": safe_args,
            "note": "This is a suggested safe version. Review before executing.",
        }


ActionNegotiator = AgentNegotiator
