import asyncio
import json
import os
import uuid
from functools import wraps
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from agentshield.modes.rollback import RollbackEngine
from agentshield.modes.simulator import ActionSimulator
from agentshield.modes.negotiator import AgentNegotiator, NegotiationResponse
from agentshield.policy.smart_scorer import SmartRiskScorer
from agentshield.policy.behavior_tracker import BehaviorTracker
from agentshield.registry.agent_registry import AgentRegistry


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
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentShield:
    def __init__(self, mode: str = "shadow", policy_path: str = None, policy: str = None):
        self.mode = mode
        self.audit_log: List[InterceptedAction] = []
        if policy and not policy_path:
            template_path = os.path.join("policies", "templates", f"{policy}.yaml")
            policy_path = template_path if os.path.exists(template_path) else None
        self.policy_path = policy_path
        self._policy_engine = None
        self._simulator = ActionSimulator()
        self.rollback_engine = RollbackEngine()
        self._smart_scorer = SmartRiskScorer()
        self._behavior_tracker = BehaviorTracker()
        self.agent_registry = AgentRegistry()
        if policy_path:
            from agentshield.policy.engine import PolicyEngine

            self._policy_engine = PolicyEngine(policy_path)
            self._behavior_tracker.configure_baselines(getattr(self._policy_engine, "baselines", {}) or {})
            self._smart_scorer.configure_policy_context(whitelists=getattr(self._policy_engine, "whitelists", {}) or {})
        self.negotiator = AgentNegotiator(self._policy_engine, risk_scorer=self._smart_scorer)

    def _resolve_agent_role(self, agent_id: str) -> Optional[str]:
        try:
            agent = self.agent_registry.get_agent(agent_id)
            if getattr(agent, "role", None):
                return agent.role
        except Exception:
            pass
        # Fallback: if policy engine defines roles, match by agent_id.
        engine = self._policy_engine
        roles = getattr(engine, "roles", None) if engine else None
        if isinstance(roles, dict) and agent_id in roles:
            return agent_id
        return None

    def reload_policy(self, policy_path: str | None = None) -> None:
        """Reload policy YAML into the active in-memory policy engine."""
        path = policy_path or self.policy_path
        if not path:
            self._policy_engine = None
            return
        from agentshield.policy.engine import PolicyEngine
        self.policy_path = path
        self._policy_engine = PolicyEngine(path)
        self._behavior_tracker.configure_baselines(getattr(self._policy_engine, "baselines", {}) or {})
        self._smart_scorer.configure_policy_context(
            whitelists=getattr(self._policy_engine, "whitelists", {}) or {}
        )
        self.negotiator = AgentNegotiator(self._policy_engine, risk_scorer=self._smart_scorer)

    async def _intercept_impl(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> InterceptedAction:
        ts = timestamp
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        elif isinstance(ts, datetime):
            ts = ts.astimezone(timezone.utc).isoformat()

        action = InterceptedAction(
            id=str(uuid.uuid4()),
            timestamp=ts,
            tool_name=tool_name,
            arguments=arguments or {},
            agent_id=agent_id,
            mode=self.mode,
            context=context or {},
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
            # Start from the policy score, then refine using contextual risk signals.
            action.risk_score = policy_result.risk_score
            action.result = {
                "policy_rule": policy_result.matched_rule,
                **(policy_result.metadata or {}),
            }
        else:
            self._score_risk(action)
            self._decide(action)
        self._prepare_preview(action)
        if self._policy_engine:
            # Even when policy is active, keep risk contextual.
            self._score_risk(action, override_decision=False)
        action.result = {
            **(action.result or {}),
            "simulation": asdict(simulation),
        }
        action.rollback_plan = rollback_plan.to_dict()
        self.audit_log.append(action)
        return action

    def intercept(
        self,
        tool_name: str,
        arguments: Optional[dict] = None,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ):
        if arguments is None:
            return self.intercept_custom(tool_name)
        return self._intercept_impl(
            tool_name=tool_name,
            arguments=arguments,
            agent_id=agent_id,
            context=context,
            timestamp=timestamp,
        )

    async def intercept_with_negotiation(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        """Intercept + if blocked, automatically return negotiation guidance."""
        action = await self._intercept_impl(
            tool_name, arguments, agent_id, context=context, timestamp=timestamp
        )
        if action.decision in ("block", "shadow"):
            negotiation = await self.negotiator.negotiate(action, None)
            return action, negotiation
        return action, None

    def intercept_with_negotiation_sync(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> tuple[InterceptedAction, Optional[NegotiationResponse]]:
        return asyncio.run(
            self.intercept_with_negotiation(
                tool_name,
                arguments,
                agent_id=agent_id,
                context=context,
                timestamp=timestamp,
            )
        )

    def intercept_sync(
        self,
        tool_name: str,
        arguments: dict,
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str | datetime] = None,
    ) -> InterceptedAction:
        return asyncio.run(
            self._intercept_impl(
                tool_name,
                arguments,
                agent_id=agent_id,
                context=context,
                timestamp=timestamp,
            )
        )

    def protect(self, tools: List[Any]) -> List[Any]:
        try:
            from agentshield.interceptor.langchain_hook import shield_all_tools

            return shield_all_tools(tools, self)
        except Exception:
            return tools

    def protect_crewai(self, crew: Any) -> Any:
        from agentshield.interceptor.crewai_hook import shield_crewai_crew

        return shield_crewai_crew(crew, self)

    def protect_openai(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from agentshield.interceptor.openai_hook import shield_openai_tools

        return shield_openai_tools(tools, self)

    def start_mcp_proxy(self, upstream: str = "localhost:3001", port: int = 3002) -> None:
        from agentshield.interceptor.mcp_proxy import run_proxy

        run_proxy(upstream=upstream, port=port)

    def protect_shell(self):
        from agentshield.interceptor.code_agent_hook import CodeAgentInterceptor

        return CodeAgentInterceptor()

    def intercept_custom(self, tool_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(fn)
            def wrapped(*args: Any, **kwargs: Any):
                _ = self.intercept_sync(tool_name=tool_name, arguments={"args": args, "kwargs": kwargs})
                return fn(*args, **kwargs)

            return wrapped

        return decorator

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

    def _score_risk(self, action: InterceptedAction, *, override_decision: bool = True) -> None:
        agent_role = self._resolve_agent_role(action.agent_id)
        parsed_ts = None
        try:
            parsed_ts = datetime.fromisoformat(action.timestamp.replace("Z", "+00:00"))
        except Exception:
            parsed_ts = None

        assessment = self._smart_scorer.score_action(
            tool_name=action.tool_name,
            arguments=action.arguments,
            agent_id=action.agent_id,
            context=getattr(action, "context", None) or {},
            agent_role=agent_role,
            timestamp=parsed_ts,
        )

        drift = self._behavior_tracker.analyze_and_record(
            agent_id=action.agent_id,
            agent_role=agent_role,
            tool_name=action.tool_name,
            arguments=action.arguments,
            risk_score=assessment.score,
            timestamp=action.timestamp,
        )

        final_score = max(0.0, min(1.0, round(assessment.score + drift.total_delta, 4)))
        # Attach behavioral/baseline signals for the chat co-pilot.
        if isinstance(action.result, dict):
            action.result.update(
                {
                    "baseline_delta": drift.baseline_delta,
                    "drift_delta": drift.drift_delta,
                    "risk_trend_alert": drift.risk_trend_alert,
                    "data_volume_alert": drift.data_volume_alert,
                    "new_tool_alert": drift.new_tool_alert,
                    "enumeration_alert": drift.enumeration_alert,
                }
            )
        # If policy set a decision, do not override it here; only refine risk.
        if override_decision:
            action.risk_score = final_score
            # Decision is set by policy engine or _decide; keep it unchanged unless no policy engine.
            return
        action.risk_score = final_score

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
        # Preserve any policy evaluation details already stored in `action.result`
        # (e.g., `policy_rule`) so the chat co-pilot and negotiation layer
        # can reference them later.
        existing = action.result or {}
        action.result = {
            **existing,
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
