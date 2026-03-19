from langchain_core.tools import BaseTool


def shield_tool(tool: BaseTool, interceptor) -> BaseTool:
    original_run = tool._run

    def shielded_run(*args, **kwargs) -> str:
        action, negotiation = interceptor.intercept_with_negotiation_sync(
            tool_name=tool.name,
            arguments=kwargs if kwargs else {"input": args[0] if args else ""},
        )
        if action.decision == "block":
            explanation = (
                (negotiation.explanation.get("human_readable") if negotiation else None)
                or "Action blocked by policy."
            )
            policy_rule = (action.result or {}).get("policy_rule", "unknown_rule")
            suggestions = negotiation.suggestions if negotiation else []
            risk_factors = (
                negotiation.explanation.get("risk_factors", []) if negotiation else []
            )
            risk_factor_text = ", ".join(
                f"{f.get('type')} ({f.get('severity')})" for f in risk_factors
            ) or "none"
            first = (
                suggestions[0].get("description")
                if len(suggestions) > 0
                else "Route through manager@yourcompany.com instead"
            )
            second = (
                suggestions[1].get("description")
                if len(suggestions) > 1
                else "Request human approval via escalation"
            )
            safe_version = negotiation.proposed_safe_action if negotiation else {}
            return (
                "[AgentShield BLOCKED]\n"
                f"Reason: {explanation}. Policy: {policy_rule}. Risk: {action.risk_score}\n"
                f"Risk factors: {risk_factor_text}\n"
                "Suggestions:\n"
                f"  1. {first}\n"
                f"  2. {second}\n"
                f"Proposed safe version: {safe_version}\n"
                "To retry with modifications, adjust your action and try again."
            )
        if action.decision == "shadow":
            return (
                f"[AgentShield] Action {action.decision}. "
                f"Tool: {tool.name}. Risk: {action.risk_score}."
            )
        if action.decision == "approve":
            return f"[AgentShield] Action requires approval. Tool: {tool.name}."
        return original_run(*args, **kwargs)

    tool._run = shielded_run
    return tool


def shield_all_tools(tools: list, interceptor) -> list:
    return [shield_tool(t, interceptor) for t in tools]
