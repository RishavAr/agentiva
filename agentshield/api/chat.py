"""
Shield Chat — answer questions about agent activity from the in-memory audit log.

Uses pattern matching and simple analytics by default; optional OpenRouter LLM
for complex queries.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agentshield.interceptor.core import AgentShield


@dataclass
class ChatResponse:
    answer: str
    data: Any
    follow_up_suggestions: List[str]
    mode: str = "basic"  # "basic" (pattern matching) or "ai-powered" (OpenRouter)


class ShieldChat:
    """Chat with AgentShield about your agents' activity."""

    def __init__(self, shield: AgentShield):
        self.shield = shield

    async def ask(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()
        if not q:
            return ChatResponse(
                answer="Ask me anything about intercepted actions, blocks, risk, or agents.",
                data={},
                follow_up_suggestions=[
                    "Give me a session summary",
                    "What are the riskiest actions?",
                    "Why were actions blocked?",
                ],
            )

        if any(w in q for w in ["why blocked", "why block", "why was", "reason"]):
            return self._explain_blocks(question)

        if any(w in q for w in ["what went wrong", "problems", "issues", "incidents"]):
            return self._summarize_issues()

        if any(w in q for w in ["risky", "dangerous", "suspicious", "high risk"]):
            return self._show_risky_actions()

        if any(w in q for w in ["summary", "overview", "status", "report"]):
            return self._generate_summary()

        if any(w in q for w in ["agent", "who", "which agent"]):
            return self._agent_analysis(question)

        if any(w in q for w in ["policy", "change", "what if", "would happen"]):
            return self._policy_simulation(question)

        if any(w in q for w in ["recommend", "suggestion", "improve", "fix"]):
            return self._recommendations()

        return self._smart_response(question)

    def _get_block_reason(self, action: Any) -> str:
        res = getattr(action, "result", None) or {}
        rule = res.get("policy_rule") if isinstance(res, dict) else None
        if rule:
            return f"Policy rule: {rule}"
        args = getattr(action, "arguments", {}) or {}
        tool = getattr(action, "tool_name", "")
        if tool == "send_email" and isinstance(args, dict):
            to = str(args.get("to", ""))
            if "@yourcompany.com" not in to:
                return "External recipient / policy block on email"
        if isinstance(args, dict) and any(
            x in str(args).upper() for x in ("DROP", "DELETE", "TRUNCATE")
        ):
            return "Destructive or sensitive data operation blocked by policy"
        return "Blocked by AgentShield policy evaluation"

    def _explain_blocks(self, question: str) -> ChatResponse:
        blocked = [a for a in self.shield.audit_log if a.decision == "block"]
        recent = blocked[-5:] if blocked else []

        explanations: List[Dict[str, Any]] = []
        for action in recent:
            explanations.append(
                {
                    "tool": action.tool_name,
                    "arguments": action.arguments,
                    "risk_score": action.risk_score,
                    "reason": self._get_block_reason(action),
                    "timestamp": action.timestamp,
                }
            )

        return ChatResponse(
            answer=f"Found {len(blocked)} blocked action(s) in the current session. "
            f"Here are the most recent (up to 5):",
            data=explanations,
            follow_up_suggestions=[
                "Show me risky actions",
                "Give me a session summary",
                "What should I change in my policies?",
            ],
        )

    def _summarize_issues(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions recorded yet — run intercepts or the live demo to populate data.",
                data={"total_blocked": 0, "high_risk_count": 0, "top_blocked_tools": []},
                follow_up_suggestions=["Give me a session summary", "Run the demo script"],
            )

        blocked = [a for a in log if a.decision == "block"]
        high_risk = [a for a in log if a.risk_score > 0.7]

        by_tool: Dict[str, int] = {}
        for a in blocked:
            by_tool[a.tool_name] = by_tool.get(a.tool_name, 0) + 1

        top_issues = [
            {"tool": k, "count": v}
            for k, v in sorted(by_tool.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        most_dangerous = max(log, key=lambda a: a.risk_score)

        return ChatResponse(
            answer=f"In this session: {len(blocked)} action(s) blocked, {len(high_risk)} high-risk action(s) detected.",
            data={
                "total_blocked": len(blocked),
                "high_risk_count": len(high_risk),
                "top_blocked_tools": top_issues,
                "most_dangerous_action": most_dangerous.to_dict(),
            },
            follow_up_suggestions=[
                "Why was the most dangerous action attempted?",
                "Which agent is causing the most blocks?",
                "Any recommendations?",
            ],
        )

    def _show_risky_actions(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions yet — nothing to rank by risk.",
                data=[],
                follow_up_suggestions=["Give me a session summary"],
            )

        risky = sorted(log, key=lambda a: a.risk_score, reverse=True)[:10]
        rows = [
            {
                "tool": a.tool_name,
                "risk": a.risk_score,
                "decision": a.decision,
                "args": a.arguments,
                "agent": a.agent_id,
            }
            for a in risky
        ]

        return ChatResponse(
            answer="Top 10 riskiest actions in the current audit log (by risk score):",
            data=rows,
            follow_up_suggestions=[
                "Explain why those were blocked or shadowed",
                "Which agents are generating the most risk?",
                "Give me recommendations",
            ],
        )

    def _agent_analysis(self, question: str) -> ChatResponse:
        log = self.shield.audit_log
        agents: Dict[str, Dict[str, Any]] = {}
        for a in log:
            aid = a.agent_id
            if aid not in agents:
                agents[aid] = {"total": 0, "blocked": 0, "risks": []}
            agents[aid]["total"] += 1
            agents[aid]["risks"].append(a.risk_score)
            if a.decision == "block":
                agents[aid]["blocked"] += 1

        for _aid, data in agents.items():
            rs = data["risks"]
            data["avg_risk"] = round(sum(rs) / len(rs), 4) if rs else 0.0
            del data["risks"]

        sorted_rows = [
            {"agent_id": aid, **stats}
            for aid, stats in sorted(
                agents.items(), key=lambda x: x[1]["avg_risk"], reverse=True
            )
        ]

        return ChatResponse(
            answer=f"Tracking {len(agents)} agent(s) in the audit log. Behavior summary:",
            data=sorted_rows,
            follow_up_suggestions=[
                "Show me risky actions",
                "Give me a session summary",
                "Any recommendations to tighten security?",
            ],
        )

    def _recommendations(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No activity yet — recommendations will be more useful after actions are intercepted.",
                data=["Run your agents through AgentShield or the live demo first."],
                follow_up_suggestions=["Give me a session summary"],
            )

        blocked = [a for a in log if a.decision == "block"]
        shadowed = [a for a in log if a.decision == "shadow"]

        recommendations: List[str] = []

        if len(blocked) > len(log) * 0.3:
            recommendations.append(
                "Over 30% of actions are blocked. Review whether policies are too strict "
                "or agents need better tool-use training."
            )

        external_blocks = [
            a
            for a in blocked
            if "external" in str(a.arguments).lower()
            or "@" in str((a.arguments or {}).get("to", ""))
        ]
        if external_blocks:
            recommendations.append(
                f"{len(external_blocks)} external communication attempt(s) blocked. "
                "Consider an allowlist for trusted external contacts."
            )

        destructive = [
            a
            for a in blocked
            if any(
                w in str(a.arguments).lower()
                for w in ("delete", "drop", "remove", "truncate")
            )
        ]
        if destructive:
            recommendations.append(
                f"{len(destructive)} destructive pattern(s) caught. Keep destructive-action policies strict."
            )

        if len(shadowed) > len(log) * 0.5:
            recommendations.append(
                "Many actions are in shadow mode — good for observation before you tighten to block/allow."
            )

        if not recommendations:
            recommendations.append(
                "Activity looks within normal parameters for this session."
            )

        return ChatResponse(
            answer="Here are recommendations based on current audit log activity:",
            data=recommendations,
            follow_up_suggestions=[
                "Show me risky actions",
                "Give me a session summary",
                "What were the top issues?",
            ],
        )

    def _generate_summary(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions recorded yet.",
                data={},
                follow_up_suggestions=["Run the demo to see actions", "Send a test intercept"],
            )

        return ChatResponse(
            answer="Session summary from the AgentShield audit log:",
            data={
                "total_actions": len(log),
                "blocked": len([a for a in log if a.decision == "block"]),
                "shadowed": len([a for a in log if a.decision == "shadow"]),
                "allowed": len([a for a in log if a.decision == "allow"]),
                "avg_risk": round(sum(a.risk_score for a in log) / len(log), 4),
                "unique_agents": len({a.agent_id for a in log}),
                "unique_tools": len({a.tool_name for a in log}),
                "highest_risk_action": max(log, key=lambda a: a.risk_score).to_dict(),
                "time_span": f"{log[0].timestamp} → {log[-1].timestamp}",
            },
            follow_up_suggestions=[
                "What went wrong?",
                "Show me risky actions",
                "Any recommendations?",
            ],
        )

    def _policy_simulation(self, question: str) -> ChatResponse:
        engine = getattr(self.shield, "_policy_engine", None)
        policy_loaded = engine is not None
        hints = []
        if policy_loaded:
            hints.append(
                "Policies are loaded from YAML; first matching rule wins for each action."
            )
        else:
            hints.append(
                "No YAML policy engine attached — decisions use smart scoring / mode defaults."
            )

        q = question.lower()
        if "email" in q and "external" in q:
            hints.append(
                "Typical pattern: external `send_email` may hit `block_external_email` if not @yourcompany.com."
            )

        return ChatResponse(
            answer="Policy simulation (rule-based): I can’t run hypothetical tool calls without arguments, "
            "but here’s how AgentShield reasons about policy today:",
            data={
                "policy_engine_active": policy_loaded,
                "notes": hints,
                "tip": "Send real intercepts with the API to see exact matched_rule in each action’s result.",
            },
            follow_up_suggestions=[
                "Why were actions blocked?",
                "Give me a session summary",
                "Any recommendations?",
            ],
        )

    def _smart_response(self, question: str) -> ChatResponse:
        return ChatResponse(
            answer=(
                "I match your question to audit-log analytics (blocks, risk, agents, summaries). "
                f'For "{question[:80]}...", try rephrasing with words like: summary, blocked, risky, agent, policy, or recommendations. '
                "Set OPENROUTER_API_KEY for richer free-form answers."
            ),
            data={"hint": 'Example: "Give me a session overview" or "Show risky actions"'},
            follow_up_suggestions=[
                "Give me a session summary",
                "What are the riskiest actions?",
                "Why were actions blocked?",
            ],
        )


class SmartChat:
    """LLM-powered chat for premium users via OpenRouter."""

    def __init__(self, shield: AgentShield, api_key: Optional[str] = None):
        self.shield = shield
        self.basic_chat = ShieldChat(shield)
        raw = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self.api_key = (raw or "").strip()
        self.has_llm = bool(self.api_key)

    async def ask(self, question: str) -> ChatResponse:
        basic_response = await self.basic_chat.ask(question)
        if not self.has_llm:
            return basic_response
        context = self._get_context()
        return await self._ask_llm(question, context, basic_response)

    def _needs_llm(self, question: str) -> bool:
        q = (question or "").lower()
        complex_indicators = [
            "compare",
            "predict",
            "write a policy",
            "what if",
            "should i",
            "is it safe",
            "analyze",
            "trend",
            "recommend changes",
            "generate report",
            "explain in detail",
            "help me understand",
            "what does this mean",
        ]
        return any(ind in q for ind in complex_indicators)

    def _get_context(self) -> Dict[str, Any]:
        log = self.shield.audit_log if hasattr(self.shield, "audit_log") else []
        return {
            "total": len(log),
            "blocked": len([a for a in log if a.decision == "block"]),
            "shadowed": len([a for a in log if a.decision == "shadow"]),
            "allowed": len([a for a in log if a.decision in ("allow", "live")]),
            "avg_risk": round(sum(a.risk_score for a in log) / max(len(log), 1), 2),
            "recent": [
                {
                    "tool": a.tool_name,
                    "decision": a.decision,
                    "risk": a.risk_score,
                    "args": a.arguments,
                    "agent": a.agent_id,
                }
                for a in log[-30:]
            ],
        }

    async def _ask_llm(
        self, question: str, context: Dict[str, Any], basic_data: ChatResponse
    ) -> ChatResponse:
        import httpx

        system_prompt = f"""You are AgentShield's security co-pilot. You help teams understand what their AI agents are doing.

Here is the current session data:
- Total actions intercepted: {context['total']}
- Blocked: {context['blocked']}
- Shadowed: {context['shadowed']}
- Allowed: {context['allowed']}
- Average risk score: {context['avg_risk']}
- Recent actions: {json.dumps(context['recent'][:20], default=str)}

Answer the user's question based on this data. Be specific, reference actual tool names and risk scores. Be concise. Suggest follow-up questions."""
        user_message = question

        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://agentshield.dev",
                        "X-Title": "AgentShield",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 1024,
                    },
                    timeout=30.0,
                )
            if response.status_code == 200:
                data = response.json()
                answer = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if answer:
                    return ChatResponse(
                        answer=answer,
                        data=basic_data.data,
                        follow_up_suggestions=[
                            "Show risky actions",
                            "Which agent is most dangerous?",
                            "Recommendations to improve security",
                        ],
                        mode="ai-powered",
                    )
        except Exception:
            pass
        return basic_data


def chat_response_to_dict(resp: ChatResponse) -> Dict[str, Any]:
    return {
        "answer": resp.answer,
        "data": resp.data,
        "follow_up_suggestions": resp.follow_up_suggestions,
        "mode": resp.mode,
    }
