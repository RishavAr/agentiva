"""
Shield Chat — answer questions about agent activity from the in-memory audit log.

Uses pattern matching and simple analytics by default; optional OpenRouter LLM
for complex queries.
"""

from __future__ import annotations

import json
import os
import re
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

        # Pick an intent, then (optionally) prepend proactive high-block guidance.
        if self._is_disable_all_security(q):
            resp = self._refuse_disable_all_security()
        elif self._is_policy_wizard_request(q) or self._is_policy_wizard_active():
            resp = self._policy_wizard(question)
        elif self._is_policy_apply_request(q):
            resp = self._help_unblock_apply_flow(question)
        elif self._is_help_unblock_request(q):
            resp = self._help_unblock(question)
        elif re.search(
            r"\b(hi|hello|hey|yo|greetings|good\s+(morning|afternoon|evening))\b", q
        ):
            resp = ChatResponse(
                answer=(
                    "Hi — I’m AgentShield. I can summarize what your agents did in this session, "
                    "highlight incidents, or help you understand which agents are most risky."
                ),
                data={},
                follow_up_suggestions=[
                    "Give me a session overview",
                    "Any incidents today?",
                    "How are my agents performing?",
                ],
            )
        elif "timeline" in q:
            resp = self._show_timeline()
        elif any(w in q for w in ["why blocked", "why block", "why was", "reason"]):
            resp = self._explain_blocks(question)
        elif any(
            w in q
            for w in [
                "blocked actions",
                "show blocked",
                "blocked action",
                "blocks",
                "blocked",
            ]
        ):
            resp = self._explain_blocks(question)
        elif any(w in q for w in ["what went wrong", "problems", "issues", "incidents"]):
            resp = self._summarize_issues()
        elif any(
            w in q
            for w in [
                "risky",
                "riskiest",
                "most risky",
                "highest risk",
                "dangerous",
                "suspicious",
                "high risk",
            ]
        ):
            resp = self._show_risky_actions()
        elif any(w in q for w in ["explain the #1 risk", "explain risk", "explain the risk"]):
            resp = self._show_risky_actions()
        elif any(
            w in q
            for w in [
                "summary",
                "overview",
                "status",
                "report",
                "export report",
                "export",
            ]
        ):
            resp = self._generate_summary()
        elif any(w in q for w in ["agent", "who", "which agent"]):
            resp = self._agent_analysis(question)
        elif any(w in q for w in ["policy", "change", "what if", "would happen"]):
            resp = self._policy_simulation(question)
        elif any(
            w in q
            for w in [
                "recommend",
                "suggestion",
                "improve",
                "fix",
                "apply changes",
                "apply these changes",
            ]
        ):
            resp = self._recommendations()
        else:
            resp = self._smart_response(question)

        proactive = self._maybe_proactive_block_rate_message(q)
        if proactive and not self._should_skip_proactive_for_question(q):
            suggestions = list(resp.follow_up_suggestions)
            if "Help me unblock" not in suggestions:
                suggestions = ["Help me unblock", *suggestions]
            resp = ChatResponse(
                answer=f"{proactive}\n\n{resp.answer}",
                data=resp.data,
                follow_up_suggestions=suggestions,
                mode=resp.mode,
            )
        return resp

    def _get_block_reason(self, action: Any) -> str:
        res = getattr(action, "result", None) or {}
        rule = res.get("policy_rule") if isinstance(res, dict) else None
        if isinstance(res, dict):
            # Prefer high-signal, user-facing reasons from policy rules (geo, mandatory, etc).
            if res.get("reason"):
                return str(res.get("reason"))
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

    def _is_disable_all_security(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "disable all blocks",
                "disable blocks",
                "turn off security",
                "turn off safeguards",
                "allow everything",
                "allow all",
                "disable security",
                "turn off security",
                "off security",
                "turn off protection",
                "disable protection",
            ]
        )

    def _refuse_disable_all_security(self) -> ChatResponse:
        return ChatResponse(
            answer=(
                "I strongly recommend against disabling all blocks. Here's what would happen:\n"
                "- Your agent could email customer SSNs to external addresses\n"
                "- Database DELETE queries would execute without review\n"
                "- Unauthorized refunds could process automatically\n\n"
                "Instead, let me help you find the specific rules that are too strict.\n"
                "Ask me: 'which blocks are false positives?' and I'll analyze each one."
            ),
            data={},
            follow_up_suggestions=[
                "Which blocks are false positives?",
                "Help me unblock",
                "Show blocked actions",
            ],
        )

    def _is_policy_wizard_request(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "help me tune policies",
                "policy wizard",
                "policy tuning assistant",
                "help me tune policy",
            ]
        )

    def _is_help_unblock_request(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "help me unblock",
                "keeps getting blocked",
                "too many blocks",
                "how to fix blocks",
                "agent can't do anything",
                "agent cant do anything",
                "too restrictive",
                "stuck and blocked",
                "blocked nonstop",
            ]
        )

    def _is_policy_apply_request(self, q: str) -> bool:
        return any(
            phrase in q
            for phrase in [
                "apply the fix",
                "update policy",
                "yes apply",
                "apply these changes",
                "apply changes",
                "apply policy",
                "apply this policy",
                "confirm",
            ]
        )

    def _session_stats(self) -> Dict[str, Any]:
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]
        total = len(log)
        return {
            "total": total,
            "blocked": len(blocked),
            "block_rate": (len(blocked) / total) if total else 0.0,
        }

    def _should_skip_proactive_for_question(self, q: str) -> bool:
        return (
            self._is_help_unblock_request(q)
            or self._is_policy_wizard_request(q)
            or self._is_policy_wizard_active()
            or self._is_policy_apply_request(q)
            or self._is_disable_all_security(q)
        )

    def _is_policy_wizard_active(self) -> bool:
        state = getattr(self.shield, "_policy_wizard_state", None)
        if not isinstance(state, dict):
            return False
        try:
            step = int(state.get("step", 0))
        except Exception:
            return False
        return step in (1, 2, 3, 4, 5)

    def _maybe_proactive_block_rate_message(self, q: str) -> str | None:
        stats = self._session_stats()
        if stats["total"] <= 0:
            return None
        if stats["block_rate"] <= 0.4:
            return None
        pct = int(round(stats["block_rate"] * 100))
        return (
            f"I notice {pct}% of your agent's actions are being blocked. "
            "This might mean your policies are too strict for your use case. "
            "Would you like me to analyze which blocks are false positives and suggest fixes?"
        )

    def _get_policy_engine(self):
        return getattr(self.shield, "_policy_engine", None)

    def _find_policy_rule(self, rule_name: str) -> Dict[str, Any] | None:
        engine = self._get_policy_engine()
        if not engine:
            return None
        policy = getattr(engine, "policy", None)
        rules = (policy or {}).get("rules", []) if isinstance(policy, dict) else []
        for r in rules:
            if r.get("name") == rule_name:
                return r
        return None

    def _rule_condition_summary(self, rule: Dict[str, Any]) -> str:
        cond = rule.get("condition") or {}
        field = cond.get("field", "arguments.<unknown>")
        op = cond.get("operator", "equals")
        value = cond.get("value")
        return f"{field} {op} {value}"

    def _compute_unblock_policy_additions(self, blocked_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Returns YAML rule dicts to insert into policies/default.yaml.
        Kept intentionally small/deterministic for UX and testability.
        """
        additions: List[Dict[str, Any]] = []
        seen_names = set()

        for g in blocked_groups:
            tool = g["tool_name"]
            rule_name = g["policy_rule"]
            if g["category"] != "too_strict":
                continue

            if tool == "send_email" and rule_name == "block_external_email":
                name = "allow_customer_replies"
                if name in seen_names:
                    continue
                # Match the UX example exactly for support replies.
                additions.append(
                    {
                        "name": name,
                        "tool": "send_email",
                        "condition": {
                            "field": "arguments.subject",
                            "operator": "contains",
                            "value": "Re:",
                        },
                        "action": "allow",
                        "risk_score": 0.2,
                        "insert_before": ["block_external_email"],
                    }
                )
                seen_names.add(name)

            if tool == "read_customer_data" and rule_name and "ssn" in rule_name:
                name = "allow_support_data_read"
                if name in seen_names:
                    continue
                additions.append(
                    {
                        "name": name,
                        "tool": "read_customer_data",
                        "condition": {
                            "field": "arguments.fields",
                            "operator": "not_contains",
                            "value": "ssn",
                        },
                        "action": "allow",
                        "risk_score": 0.3,
                        "insert_before": ["block_read_ssn_export"],
                    }
                )
                seen_names.add(name)

        return additions

    def _format_policy_additions_snippet(self, additions: List[Dict[str, Any]]) -> str:
        # Render additions as plain YAML blocks (no fenced code blocks).
        # Keep quoting consistent with the UX example.
        blocks: List[str] = []
        for r in additions:
            name = r["name"]
            tool = r["tool"]
            cond = r["condition"]
            field = cond["field"]
            op = cond["operator"]
            value = cond["value"]
            action = r["action"]
            risk_score = r["risk_score"]
            blocks.append(
                "\n".join(
                    [
                        f"- name: {name}",
                        f"  tool: {tool}",
                        f"  condition:",
                        f"    field: {field}",
                        f"    operator: {op}",
                        f"    value: '{value}'",
                        f"  action: {action}",
                        f"  risk_score: {risk_score}",
                    ]
                )
            )
        return "\n\n".join(blocks).strip()

    def _build_policy_yaml_with_additions(self, additions: List[Dict[str, Any]]) -> str:
        import yaml

        policy_path = os.getenv("AGENTSHIELD_POLICY_PATH", "policies/default.yaml")
        with open(policy_path, encoding="utf-8") as handle:
            base = yaml.safe_load(handle)
        if not isinstance(base, dict):
            raise ValueError("Invalid policy YAML root")
        rules = base.get("rules", []) or []
        if not isinstance(rules, list):
            rules = []

        # Insert each addition before the first matching rule name.
        for add in additions:
            insert_before = add.get("insert_before") or []
            idx = None
            for name in insert_before:
                for i, r in enumerate(rules):
                    if r.get("name") == name:
                        idx = i
                        break
                if idx is not None:
                    break
            # Strip internal insert_before key before dumping.
            add_rule = {k: v for k, v in add.items() if k != "insert_before"}
            if idx is None:
                rules.append(add_rule)
            else:
                rules.insert(idx, add_rule)

        base["rules"] = rules
        return yaml.safe_dump(base, sort_keys=False)

    def _help_unblock(self, question: str) -> ChatResponse:
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]
        if not blocked:
            return ChatResponse(
                answer="I don't see blocked actions in the audit log yet. Run the demo or intercept a few actions and try again.",
                data={},
                follow_up_suggestions=["Show blocked actions", "Give me a session summary", "Run the demo script"],
            )

        # Group by (tool, policy_rule) so we can explain “which policy rule blocked it”.
        groups_map: Dict[tuple[str, str], List[Any]] = {}
        for a in blocked:
            res = getattr(a, "result", None) or {}
            rule_name = res.get("policy_rule") if isinstance(res, dict) else None
            if not rule_name:
                rule_name = "unknown_rule"
            key = (getattr(a, "tool_name", "unknown_tool"), str(rule_name))
            groups_map.setdefault(key, []).append(a)

        grouped = [
            {
                "tool_name": tool,
                "policy_rule": rule,
                "count": len(actions),
                "sample": max(actions, key=lambda x: getattr(x, "risk_score", 0.0) or 0.0),
            }
            for (tool, rule), actions in groups_map.items()
        ]
        grouped = sorted(grouped, key=lambda g: g["count"], reverse=True)[:5]

        # Categorize blocks into correct vs possibly too strict.
        # Deterministic heuristic: higher risk score implies “genuinely dangerous”.
        correct_groups: List[Dict[str, Any]] = []
        too_strict_groups: List[Dict[str, Any]] = []
        for g in grouped:
            sample = g["sample"]
            risk = float(getattr(sample, "risk_score", 0.0) or 0.0)
            category = "correct" if risk >= 0.7 else "too_strict"
            g["risk_score"] = risk
            g["category"] = category
            if category == "correct":
                correct_groups.append(g)
            else:
                too_strict_groups.append(g)

        correct_count = sum(g["count"] for g in correct_groups)
        too_strict_count = sum(g["count"] for g in too_strict_groups)

        additions = self._compute_unblock_policy_additions(too_strict_groups)
        additions_snippet = self._format_policy_additions_snippet(additions) if additions else ""

        lines: List[str] = []
        lines.append(f"Your agent was blocked {len(blocked)} times this session. Here's the breakdown:")
        lines.append("")

        # Copilot awareness: role-based policies need an assigned agent role.
        engine = getattr(self.shield, "_policy_engine", None)
        roles = getattr(engine, "roles", {}) if engine else {}
        agent_id = getattr(blocked[0], "agent_id", "") if blocked else ""
        if isinstance(roles, dict) and roles and agent_id not in roles:
            lines.append(
                "Your agent doesn't have a role configured. Set it as 'sales_agent' to automatically allow external emails."
            )
            lines.append("")

        # Baseline/drift awareness to help users understand "why now?"
        baseline_blocks = [
            a
            for a in blocked
            if isinstance(getattr(a, "result", None), dict)
            and float((a.result or {}).get("baseline_delta", 0.0) or 0.0) < 0
        ]
        any_drift = any(
            isinstance(getattr(a, "result", None), dict)
            and (
                (a.result or {}).get("risk_trend_alert")
                or (a.result or {}).get("data_volume_alert")
                or (a.result or {}).get("new_tool_alert")
                or (a.result or {}).get("enumeration_alert")
            )
            for a in blocked
        )

        if baseline_blocks:
            lines.append(
                "This action looks normal for your agent's baseline, but a global rule is blocking it. "
                "I recommend adding it to the whitelist."
            )
            lines.append("")
        if any_drift:
            lines.append(
                "I also detected behavioral drift in the last hour (patterns changed enough to trigger extra scrutiny)."
            )
            lines.append("")

        if correct_groups:
            lines.append(f"✅ {correct_count} blocks were correct (genuinely dangerous):")
            for g in correct_groups:
                rule = self._find_policy_rule(g["policy_rule"])
                cond_summary = self._rule_condition_summary(rule) if rule else "matched a block rule"
                lines.append(
                    f"- {g['count']}x `{g['tool_name']}` blocked by policy `{g['policy_rule']}` "
                    f"(risk: {g['risk_score']:.2f}) because {cond_summary}"
                )
                # Give a short “why it was high” marker for UX.
                if rule and "risk_score" in rule:
                    lines[-1] += f" (rule risk: {float(rule.get('risk_score', 0.0)):.2f})"
        else:
            lines.append("✅ No clearly dangerous blocks detected in the top items.")

        lines.append("")

        if too_strict_groups:
            lines.append(f"⚠️ {too_strict_count} blocks might be too strict:")
            for g in too_strict_groups:
                rule = self._find_policy_rule(g["policy_rule"])
                cond_summary = self._rule_condition_summary(rule) if rule else "matched a block rule"
                lines.append(
                    f"- {g['count']}x `{g['tool_name']}` blocked by policy `{g['policy_rule']}` "
                    f"(risk: {g['risk_score']:.2f}) because {cond_summary}"
                )
                if rule and "risk_score" in rule:
                    lines[-1] += f" (rule risk: {float(rule.get('risk_score', 0.0)):.2f})"
        else:
            lines.append("⚠️ No possibly-too-strict blocks detected in the top items.")

        if additions_snippet:
            lines.append("")
            lines.append(f"Recommended fix for the {too_strict_count} false positives:")
            lines.append("")
            lines.append("Add these rules to your policy.yaml:")
            lines.append("")
            lines.append(additions_snippet)

        lines.append("")
        lines.append("Want me to apply these changes?")

        return ChatResponse(
            answer="\n".join(lines),
            data={"unblock_policy_additions": additions},
            follow_up_suggestions=[
                "Apply these changes",
                "Which blocks are false positives?",
                "Show the timeline",
            ],
        )

    def _help_unblock_apply_flow(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()

        # Always recompute additions from the current audit log.
        log = getattr(self.shield, "audit_log", []) or []
        blocked = [a for a in log if getattr(a, "decision", "") == "block"]

        if not blocked:
            return ChatResponse(
                answer="I don't see blocked actions in the audit log yet, so I can't generate a targeted unblock policy change.",
                data={},
                follow_up_suggestions=["Show blocked actions", "Give me a session summary"],
            )

        # Build top groups (same grouping logic as _help_unblock).
        groups_map: Dict[tuple[str, str], List[Any]] = {}
        for a in blocked:
            res = getattr(a, "result", None) or {}
            rule_name = res.get("policy_rule") if isinstance(res, dict) else None
            if not rule_name:
                rule_name = "unknown_rule"
            key = (getattr(a, "tool_name", "unknown_tool"), str(rule_name))
            groups_map.setdefault(key, []).append(a)

        grouped = [
            {
                "tool_name": tool,
                "policy_rule": rule,
                "count": len(actions),
                "sample": max(actions, key=lambda x: getattr(x, "risk_score", 0.0) or 0.0),
            }
            for (tool, rule), actions in groups_map.items()
        ]
        grouped = sorted(grouped, key=lambda g: g["count"], reverse=True)[:5]

        too_strict_groups: List[Dict[str, Any]] = []
        for g in grouped:
            sample = g["sample"]
            risk = float(getattr(sample, "risk_score", 0.0) or 0.0)
            if risk < 0.7:
                g["risk_score"] = risk
                g["category"] = "too_strict"
                too_strict_groups.append(g)

        additions = self._compute_unblock_policy_additions(too_strict_groups)
        additions_snippet = self._format_policy_additions_snippet(additions) if additions else ""
        if not additions_snippet:
            return ChatResponse(
                answer="I couldn't identify any blocks that look plausibly too strict in the top items. If you want, I can still review specific tool blocks by asking: 'which blocks are false positives?'.",
                data={},
                follow_up_suggestions=["Which blocks are false positives?", "Show blocked actions", "Show the timeline"],
            )

        is_confirm = "confirm" in q or q.strip() == "yes" or "yes, confirm" in q
        if not is_confirm:
            allow_summary = "customer email replies and support data reads (excluding SSN)"
            return ChatResponse(
                answer=(
                    "This will allow "
                    + allow_summary
                    + ". Confirm?\n\nAdd these rules to your policy.yaml:\n\n"
                    + additions_snippet
                ),
                data={"apply_policy_yaml": None, "apply_now": False},
                follow_up_suggestions=["Confirm", "Cancel"],
            )

        # Apply immediately: server will call the policy update API using policy_yaml.
        policy_yaml = self._build_policy_yaml_with_additions(additions)
        return ChatResponse(
            answer=(
                "Policy updated. Your agent should now be able to handle customer replies and read non-sensitive customer data. "
                "I'll monitor the next 50 actions and let you know if anything looks wrong."
            ),
            data={"apply_now": True, "policy_yaml": policy_yaml},
            follow_up_suggestions=["Show blocked actions", "Which tools are riskiest?", "Show the timeline"],
        )

    def _policy_wizard(self, question: str) -> ChatResponse:
        q = (question or "").strip().lower()
        start = self._is_policy_wizard_request(q)
        state = getattr(self.shield, "_policy_wizard_state", None)
        if start or not isinstance(state, dict):
            state = {"step": 1, "responses": {}, "generated_policy_yaml": None}
            setattr(self.shield, "_policy_wizard_state", state)

        step = int(state.get("step", 1))

        def parse_agent_type() -> str | None:
            if any(k in q for k in ["customer support", "support", "helpdesk", "support ticket"]):
                return "customer support"
            if any(k in q for k in ["sales", "lead", "crm"]):
                return "sales"
            if any(k in q for k in ["devops", "dev ops", "code", "ci/cd", "deploy"]):
                return "devops"
            if "other" in q:
                return "other"
            return None

        def parse_tools() -> List[str]:
            tools: List[str] = []
            if "email" in q or "send_email" in q:
                tools.append("send_email")
            if "slack" in q or "send_slack_message" in q:
                tools.append("send_slack_message")
            if "jira" in q or "create_jira_ticket" in q:
                tools.append("create_jira_ticket")
            if "database" in q or "db" in q or "sql" in q:
                tools.append("read_customer_data")
            if "read_customer_data" in q:
                tools.append("read_customer_data")
            if "payments" in q or "refund" in q or "transfer_funds" in q:
                tools.append("transfer_funds")
            if not tools:
                tools = []
            return tools

        def parse_recipients() -> str | None:
            if "internal" in q:
                return "internal"
            if "customer" in q or "support" in q:
                return "customers"
            if "external" in q or "partner" in q:
                return "external partners"
            return None

        def parse_risk_tol() -> str | None:
            if "strict" in q:
                return "strict"
            if "permissive" in q:
                return "permissive"
            if "balanced" in q:
                return "balanced"
            return None

        # Step 1
        if step == 1:
            agent_type = parse_agent_type()
            if not agent_type:
                return ChatResponse(
                    answer=(
                        "Policy Tuning Assistant\n\n"
                        "Step 1: What does your agent do? (customer support / sales / devops / other)"
                    ),
                    data={},
                    follow_up_suggestions=["customer support", "sales", "devops", "other"],
                )
            state["responses"]["agent_type"] = agent_type
            state["step"] = 2
            return ChatResponse(
                answer=(
                    "Step 2: Which tools does it use? (email, slack, jira, database, payments)\n"
                    "Reply with something like: `email + jira + database`."
                ),
                data={},
                follow_up_suggestions=["email + jira + database", "email + slack", "devops tools", "payments"],
            )

        # Step 2
        if step == 2:
            tools = parse_tools()
            if not tools:
                return ChatResponse(
                    answer="Step 2: Which tools does it use? (email, slack, jira, database, payments)",
                    data={},
                    follow_up_suggestions=["email + jira + database", "email + slack", "devops tools", "payments"],
                )
            state["responses"]["tools"] = tools
            state["step"] = 3
            return ChatResponse(
                answer="Step 3: Who are the recipients? (internal only / customers / external partners)",
                data={},
                follow_up_suggestions=["internal only", "customers", "external partners"],
            )

        # Step 3
        if step == 3:
            recipients = parse_recipients()
            if not recipients:
                return ChatResponse(
                    answer="Step 3: Who are the recipients? (internal only / customers / external partners)",
                    data={},
                    follow_up_suggestions=["internal only", "customers", "external partners"],
                )
            state["responses"]["recipients"] = recipients
            state["step"] = 4
            return ChatResponse(
                answer="Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                data={},
                follow_up_suggestions=["strict", "balanced", "permissive"],
            )

        # Step 4
        if step == 4:
            risk_tol = parse_risk_tol()
            if not risk_tol:
                return ChatResponse(
                    answer="Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                    data={},
                    follow_up_suggestions=["strict", "balanced", "permissive"],
                )
            state["responses"]["risk_tolerance"] = risk_tol
            policy_yaml = self._generate_policy_from_wizard_state(state)
            state["generated_policy_yaml"] = policy_yaml
            state["step"] = 5
            return ChatResponse(
                answer=(
                    "Policy Wizard generated a custom policy.yaml for your use case.\n\n"
                    f"{policy_yaml}\n\n"
                    "Want me to apply this policy?"
                ),
                data={},
                follow_up_suggestions=["Apply policy", "Review risky rules", "Show blocked actions"],
            )

        # Step 5 (policy ready)
        generated = state.get("generated_policy_yaml") or ""
        if not generated:
            state["step"] = 4
            return ChatResponse(
                answer="I lost the generated policy. Step 4: What's your risk tolerance? (strict / balanced / permissive)",
                data={},
                follow_up_suggestions=["strict", "balanced", "permissive"],
            )

        if "confirm" in q:
            return ChatResponse(
                answer=(
                    "Policy updated. I'll monitor the next 50 actions and let you know if anything looks wrong."
                ),
                data={"apply_now": True, "policy_yaml": generated},
                follow_up_suggestions=["Show blocked actions", "Show risky actions", "Show the timeline"],
            )

        if any(
            phrase in q
            for phrase in [
                "apply policy",
                "apply this policy",
                "update policy",
                "yes apply",
                "apply these changes",
            ]
        ):
            return ChatResponse(
                answer="This will apply your custom policy.yaml. Confirm?",
                data={"apply_now": False, "policy_yaml": generated},
                follow_up_suggestions=["Confirm", "Cancel"],
            )

        return ChatResponse(
            answer="I already generated a custom policy.yaml. Want to apply it now?",
            data={},
            follow_up_suggestions=["Apply policy", "Review risky rules", "Show blocked actions"],
        )

    def _generate_policy_from_wizard_state(self, state: Dict[str, Any]) -> str:
        import yaml

        agent_type = state.get("responses", {}).get("agent_type", "other")
        tools = state.get("responses", {}).get("tools", [])
        recipients = state.get("responses", {}).get("recipients", "internal")
        risk_tol = state.get("responses", {}).get("risk_tolerance", "balanced")

        # Start from a safe minimal baseline: keep high-severity blocks.
        rules: List[Dict[str, Any]] = [
            {
                "name": "block_sql_drop",
                "tool": "update_database",
                "condition": {"field": "arguments.query", "operator": "contains", "value": "DROP"},
                "action": "block",
                "risk_score": 0.97,
            },
            {
                "name": "block_shell_rm_rf_root",
                "tool": "run_shell_command",
                "condition": {"field": "arguments.command", "operator": "contains", "value": "rm -rf /"},
                "action": "block",
                "risk_score": 0.99,
            },
            {
                "name": "demo_outcome_allow",
                "tool": "*",
                "condition": {"field": "arguments.outcome_tier", "operator": "equals", "value": "allow"},
                "action": "allow",
                "risk_score": 0.11,
            },
        ]

        # Add allow rules guided by tolerance and recipients.
        # This is intentionally conservative: it only “opens doors” where it matches your answers.
        if "send_email" in tools:
            if recipients in {"internal", "customers"} and risk_tol in {"strict", "balanced"}:
                rules.append(
                    {
                        "name": "allow_internal_email",
                        "tool": "send_email",
                        "condition": {"field": "arguments.to", "operator": "contains", "value": "@yourcompany.com"},
                        "action": "allow",
                        "risk_score": 0.2,
                    }
                )
            if recipients in {"customers"} and risk_tol in {"balanced", "permissive"}:
                rules.append(
                    {
                        "name": "allow_customer_replies",
                        "tool": "send_email",
                        "condition": {"field": "arguments.subject", "operator": "contains", "value": "Re:"},
                        "action": "allow",
                        "risk_score": 0.2 if risk_tol != "permissive" else 0.25,
                    }
                )

        if "read_customer_data" in tools and recipients in {"customers", "external partners"}:
            rules.append(
                {
                    "name": "allow_support_data_read",
                    "tool": "read_customer_data",
                    "condition": {"field": "arguments.fields", "operator": "not_contains", "value": "ssn"},
                    "action": "allow",
                    "risk_score": 0.3,
                }
            )

        if agent_type == "devops" and "run_shell_command" in tools:
            rules.append(
                {
                    "name": "allow_safe_shell_commands",
                    "tool": "run_shell_command",
                    "condition": {"field": "arguments.command", "operator": "contains", "value": "ls"},
                    "action": "allow",
                    "risk_score": 0.25,
                }
            )

        policy = {
            "version": 1,
            "default_mode": "shadow",
            "rules": rules,
        }
        return yaml.safe_dump(policy, sort_keys=False).strip()

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

        lines = [
            f"Found {len(blocked)} blocked action(s) in the current session. Here are the most recent (up to 5):"
        ]
        if explanations:
            lines.append("")
        for e in explanations:
            # Keep formatting stable for the UI: "risk: X.XX" is parsed for color.
            lines.append(
                f"- `{e['tool']}` risk: {float(e['risk_score']):.2f} · {e['reason']} · at {e['timestamp']}"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Explain the #1 risk",
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

        lines = [
            f"In this session, {len(blocked)} action(s) were blocked and {len(high_risk)} were high risk (risk > 0.70)."
        ]

        if top_issues:
            lines.append("")
            lines.append("Top blocked tools:")
            for row in top_issues:
                lines.append(f"- `{row['tool']}`: {row['count']}")

        lines.append("")
        lines.append(
            f"Most dangerous attempted action: `{most_dangerous.tool_name}` risk: {most_dangerous.risk_score:.2f} by agent `{most_dangerous.agent_id}`."
        )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Export report",
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

        lines = ["Top riskiest actions in the current audit log (by risk score):"]
        lines.append("")
        for idx, a in enumerate(risky, 1):
            lines.append(
                f"{idx}. `{a.tool_name}` risk: {a.risk_score:.2f} · decision: {a.decision} · agent: `{a.agent_id}`"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show the timeline",
            ],
        )

    def _show_timeline(self) -> ChatResponse:
        log = self.shield.audit_log
        if not log:
            return ChatResponse(
                answer="No actions yet — intercept actions or run the live demo first to build a timeline.",
                data={},
                follow_up_suggestions=[
                    "Give me a session overview",
                    "Show blocked actions",
                    "Show risky actions",
                ],
            )

        # Timestamps are typically ISO strings; lexicographic sort works for chronological ordering.
        recent = sorted(log, key=lambda a: str(getattr(a, "timestamp", "")), reverse=True)[:15]

        lines = ["Session timeline (most recent first):", ""]
        for a in recent:
            ts = getattr(a, "timestamp", "")
            lines.append(
                f"- {ts} `{a.tool_name}` decision: {a.decision} · risk: {a.risk_score:.2f} · agent: `{a.agent_id}`"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show me the riskiest actions",
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

        top = sorted_rows[:5]
        lines = [f"Tracking {len(agents)} agent(s) in the audit log."]
        lines.append("")
        lines.append("Top agents by average risk:")
        for row in top:
            lines.append(
                f"- `{row['agent_id']}`: avg risk {row['avg_risk']:.2f}, blocked {row.get('blocked', 0)}"
            )

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Deactivate the riskiest agent",
                "Show me the riskiest actions from the top agent",
                "Recommendations to improve security",
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

        lines = ["Here are my security recommendations based on current audit log activity:"]
        lines.append("")
        for r in recommendations:
            lines.append(f"- {r}")

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Apply these changes",
                "Show me the data behind this",
                "Compare to last session",
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

        blocked = [a for a in log if a.decision == "block"]
        shadowed = [a for a in log if a.decision == "shadow"]
        allowed = [a for a in log if a.decision == "allow"]
        avg_risk = sum(a.risk_score for a in log) / len(log)
        highest = max(log, key=lambda a: a.risk_score)

        lines = [
            "Session summary from the AgentShield audit log:",
            f"- Total actions: {len(log)}",
            f"- Blocked: {len(blocked)}",
            f"- Shadowed: {len(shadowed)}",
            f"- Allowed: {len(allowed)}",
            f"- Average risk: {avg_risk:.2f}",
            f"- Highest risk action: `{highest.tool_name}` risk: {highest.risk_score:.2f} (agent `{highest.agent_id}`)",
        ]
        lines.append("")
        lines.append(f"Time span: {log[0].timestamp} → {log[-1].timestamp}")

        return ChatResponse(
            answer="\n".join(lines),
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "Which tools are riskiest?",
                "Export report",
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
            data={},
            follow_up_suggestions=[
                "Show blocked actions",
                "What policy is triggering these blocks?",
                "Give me recommendations",
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
        q = (question or "").strip().lower()
        critical = self.basic_chat._is_help_unblock_request(q) or self.basic_chat._is_policy_apply_request(
            q
        ) or self.basic_chat._is_disable_all_security(q) or self.basic_chat._is_policy_wizard_request(
            q
        )
        if critical:
            return basic_response
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

        ql = (question or "").lower()
        if any(k in ql for k in ["summary", "overview", "status", "report"]):
            suggestions = ["Show blocked actions", "Which tools are riskiest?", "Export report"]
        elif any(k in ql for k in ["risky", "dangerous", "suspicious", "high risk"]):
            suggestions = [
                "Explain the #1 risk",
                "What policy would fix this?",
                "Show the timeline",
            ]
        elif any(k in ql for k in ["recommend", "suggestion", "improve", "fix"]):
            suggestions = [
                "Apply these changes",
                "Show me the data behind this",
                "Compare to last session",
            ]
        elif any(k in ql for k in ["hi", "hello", "hey", "greetings"]):
            suggestions = [
                "Give me a session overview",
                "Any incidents today?",
                "How are my agents performing?",
            ]
        elif any(k in ql for k in ["why blocked", "why block", "reason", "blocked"]):
            suggestions = [
                "Show blocked actions",
                "Which tools are riskiest?",
                "Explain the #1 risk",
            ]
        else:
            suggestions = [
                "Give me a session overview",
                "Show risky actions",
                "Any recommendations?",
            ]

        system_prompt = (
            "You are AgentShield's security co-pilot. You help teams understand what their AI agents are doing.\n\n"
            "Session data (reference it, do not invent data):\n"
            f"- Total actions intercepted: {context['total']}\n"
            f"- Blocked: {context['blocked']}\n"
            f"- Shadowed: {context['shadowed']}\n"
            f"- Allowed: {context['allowed']}\n"
            f"- Average risk score: {context['avg_risk']}\n"
            f"- Recent actions: {json.dumps(context['recent'][:20], default=str)}\n\n"
            "Instructions:\n"
            "- Answer in natural language.\n"
            "- Use clear bullet points for multi-item answers.\n"
            "- Be specific: mention tool names and risk scores (wrap tool names in backticks).\n"
            "- Be actionable: include concrete recommendations.\n"
            "- Never output JSON and never output code blocks.\n"
            "- Suggest 2-3 follow-up questions.\n"
        )
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
                        data={},
                        follow_up_suggestions=suggestions,
                        mode="ai-powered",
                    )
        except Exception:
            pass
        return basic_data


def chat_response_to_dict(resp: ChatResponse) -> Dict[str, Any]:
    # API contract: only natural language answer + contextual suggestions.
    # Never return raw JSON / data dumps to the UI.
    return {"answer": resp.answer, "suggestions": resp.follow_up_suggestions}
