from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from agentiva.api.chat import ALLOW_ONE_PHRASES
from agentiva.db.database import (
    add_chat_message,
    count_action_logs_by_decision,
    count_all_action_logs,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_actions,
    list_chat_messages,
    list_chat_sessions,
    update_chat_session_title,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat-fallback"])

# In-memory fallback for environments where DB chat persistence is unavailable.
chat_sessions: Dict[str, Dict[str, Any]] = {}
chat_messages: Dict[str, List[Dict[str, Any]]] = {}


class ChatMessageRequest(BaseModel):
    message: str = Field(..., validation_alias=AliasChoices("message", "content"), min_length=1, max_length=4000)


session_context: Dict[str, Dict[str, Any]] = {}

followup_phrases: List[str] = [
    "show full details",
    "full details",
    "more details",
    "show details",
    "tell me more",
    "more",
    "elaborate",
    "expand",
    "dig deeper",
    "show me more",
    "explain more",
    "go deeper",
    "details",
    "yes",
    "yeah",
    "yep",
    "sure",
    "ok",
    "please",
    "do it",
    "show me",
    "let me see",
    "continue",
]

tool_keywords: Dict[str, str] = {
    "email": "%email%",
    "send_email": "%email%",
    "send email": "%email%",
    "send mail": "%email%",
    "mail": "%email%",
    "database": "%database%",
    "db": "%database%",
    "sql": "%database%",
    "query": "%database%",
    "update_database": "%database%",
    "slack": "%slack%",
    "message": "%slack%",
    "shell": "%shell%",
    "command": "%command%",
    "terminal": "%shell%",
    "run_shell": "%shell%",
    "api": "%api%",
    "endpoint": "%api%",
    "external": "%api%",
    "customer": "%customer%",
    "read_customer": "%customer%",
    "ticket": "%ticket%",
    "jira": "%ticket%",
}


def _arg_hint(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("to", "query", "message", "command", "subject"):
        if key in arguments and arguments[key]:
            v = str(arguments[key])
            return f"{key}={v[:80]}"
    return ""


def _action_path_from_args(arguments: Any) -> str:
    """Best-effort file path for scanners (path / file / filepath)."""
    if not isinstance(arguments, dict):
        return ""
    for key in ("path", "file", "filepath"):
        v = arguments.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _describe_blocked_tool(tool: str, args: Any) -> str:
    tl = (tool or "").lower()
    if isinstance(args, dict) and args.get("credentials_found"):
        return "hardcoded credentials"
    if tl == "read_customer_data":
        return "exposes PII (SSN/credit card)"
    if tl == "run_shell_command":
        return "dangerous shell patterns"
    if tl == "install_package":
        return "compromised or risky dependency"
    return f"`{tool}` blocked by policy"


def _plain_explain_blocked(top: Dict[str, Any]) -> str:
    """Short, plain-English explanation for the top blocked row (co-pilot 'I didn't get it' path)."""
    tool = str(top.get("tool") or "unknown")
    agent = str(top.get("agent") or "unknown")
    risk = float(top.get("risk") or 0.0)
    args = top.get("args")
    tl = tool.lower()

    if "email" in tl or "mail" in tl:
        to_s = ""
        subj = ""
        if isinstance(args, dict):
            to_s = str(args.get("to", "") or "")
            subj = str(args.get("subject", "") or "")
        looks_external = bool(to_s) and ("@yourcompany.com" not in to_s.lower())
        parts = [
            "**In plain English:**",
            "",
        ]
        if looks_external:
            parts.append(
                f"Your agent tried to send an email to **{to_s}**. That address looks **outside** your company domain."
            )
            parts.append(
                "The policy blocked it so sensitive or customer data is not emailed to external addresses by mistake. "
                "**Nothing was sent** — the block happened before the message left your environment."
            )
        else:
            parts.append(
                f"Your agent tried to use **{tool}**. The destination or content still looked high-risk, "
                "so Agentiva stopped it before the email went out."
            )
        if subj:
            snip = subj[:70] + ("…" if len(subj) > 70 else "")
            parts.append(f"The subject line included: “{snip}”.")
        return "\n".join(parts)

    if any(x in tl for x in ("database", "sql", "query")):
        return "\n".join(
            [
                "**In plain English:**",
                "",
                f"The **{tool}** call looked like it could change or expose important data in a risky way. "
                "Agentiva blocked it so the database never ran that operation.",
            ]
        )

    return "\n".join(
        [
            "**In plain English:**",
            "",
            f"Agent **{agent}** tried to run **`{tool}`** with a very high risk score ({risk:.2f}).",
            "The system looks at the tool, the payload, and your policies, then blocks actions that could cause harm "
            "or leak data. **Nothing from that call was executed.**",
        ]
    )


async def fetch_audit_data(db: Any = None) -> Dict[str, Any]:
    """Fetch relevant audit data in one go (DB-grounded, async helpers)."""
    total = await count_all_action_logs()
    blocked = await count_action_logs_by_decision("block")
    shadowed = await count_action_logs_by_decision("shadow")
    allowed = await count_action_logs_by_decision("allow") + await count_action_logs_by_decision("approve")
    block_rows = await list_actions(decision="block", limit=5)
    shadow_rows = await list_actions(decision="shadow", limit=5)
    block_agg = await list_actions(decision="block", limit=2000)
    shadow_agg = await list_actions(decision="shadow", limit=2000)

    agent_block_counts: Dict[str, int] = {}
    for r in block_agg:
        agent_block_counts[r.agent_id] = agent_block_counts.get(r.agent_id, 0) + 1

    credential_shadow_by_agent: Dict[str, int] = {}
    for r in shadow_agg:
        args = r.arguments if isinstance(r.arguments, dict) else {}
        if isinstance(args, dict) and args.get("credentials_found"):
            credential_shadow_by_agent[r.agent_id] = credential_shadow_by_agent.get(r.agent_id, 0) + 1

    top_blocked = []
    for r in block_rows:
        args = r.arguments if isinstance(r.arguments, dict) else {}
        path = _action_path_from_args(args)
        top_blocked.append(
            {
                "tool": r.tool_name,
                "risk": float(r.risk_score),
                "args": r.arguments,
                "path": path,
                "agent": r.agent_id,
                "time": r.timestamp.isoformat() if hasattr(r, "timestamp") else "",
            }
        )
    top_shadowed = [
        {
            "tool": r.tool_name,
            "risk": float(r.risk_score),
            "args": r.arguments,
            "path": _action_path_from_args(r.arguments if isinstance(r.arguments, dict) else {}),
            "agent": r.agent_id,
            "time": r.timestamp.isoformat() if hasattr(r, "timestamp") else "",
        }
        for r in shadow_rows
    ]
    agents_map: Dict[str, int] = {}
    for r in await list_actions(limit=500):
        agents_map[r.agent_id] = agents_map.get(r.agent_id, 0) + 1
    agents = [{"id": k, "count": v} for k, v in sorted(agents_map.items(), key=lambda x: x[1], reverse=True)]
    return {
        "total": total,
        "blocked": blocked,
        "shadowed": shadowed,
        "allowed": allowed,
        "block_rate": round((blocked / total * 100) if total > 0 else 0, 1),
        "top_blocked": top_blocked,
        "top_shadowed": top_shadowed,
        "agents": agents,
        "agent_block_counts": agent_block_counts,
        "credential_shadow_by_agent": credential_shadow_by_agent,
        "has_data": total > 0,
    }

def classify_intent(msg: str, ctx: Dict[str, Any]) -> str:
    """Classify user intent. Broader rules run before the generic fallback."""
    s = msg.lower().strip()
    m = s.rstrip("?!.,;")
    words = set(s.replace("?", " ").replace(".", " ").split())
    last = ctx.get("last_topic") or "general"

    # --- One-off allow (shadow -> allow) ---
    if any(p in m for p in ALLOW_ONE_PHRASES) or re.match(r"^\s*allow\b", m):
        return "allow_one"

    # --- Shadowed actions ---
    if any(
        k in m
        for k in (
            "view shadowed actions",
            "shadowed actions",
            "show shadowed",
            "show shadowed actions",
            "review shadowed",
            "review shadowed actions",
            "shadowed",
        )
    ):
        return "shadowed"

    # --- Redirect / rejection (before short greetings like "no") ---
    if m in {"no", "nah", "nope", "not really", "never mind", "nevermind", "cancel"} or m.startswith("no thanks"):
        return "redirect"

    # --- Positive responses to suggestions ---
    if m in {
        "yes",
        "yeah",
        "yep",
        "sure",
        "ok",
        "okay",
        "please",
        "do it",
        "go ahead",
        "lets go",
        "let's go",
        "show me",
    }:
        return f"followup_{last}"

    # --- Numbers (e.g. "1" or "#1") ---
    if m.replace("#", "").strip().isdigit():
        return f"followup_{last}"

    # --- Single-word tool names ---
    if m in {"email", "database", "slack", "shell", "api", "jira", "ticket"}:
        return "tool_analysis"

    # --- Setup / onboarding (exclude bare "start" as greeting) ---
    if m != "start" and (
        any(
            w in m
            for w in (
                "setup",
                "install",
                "begin",
                "configure",
                "connect",
                "integrate",
                "how to",
                "getting started",
                "set up",
                "set this up",
            )
        )
        or ("start" in m and len(m) > 5)
    ):
        return "setup"

    # --- Export subtypes before generic export ---
    if any(w in s for w in ("export soc2", "soc2 export", "download soc2")):
        return "export_soc2"
    if any(w in s for w in ("export hipaa", "hipaa export", "download hipaa")):
        return "export_hipaa"
    if any(w in s for w in ("export pci", "export pci-dss", "download pci", "download pci-dss")):
        return "export_pci"
    if "export all" in s or "download all" in s:
        return "export_all"
    if any(w in s for w in ("export", "download", "report", "pdf", "generate report", "compliance report")):
        return "export"

    # --- Safety / production readiness ---
    if any(w in s for w in ("safe", "secure", "ready", "production", "go live", "deploy")):
        return "safety_assessment"
    if any(w in s for w in ("is everything ok", "is everything okay")):
        return "safety_assessment"

    # --- Short follow-ups (before wh-questions so "why?" is not forced to overview) ---
    if m in {"why", "why?", "explain", "tell me more", "more details", "elaborate", "how", "how?"}:
        return f"followup_{last}"

    # --- "Explain again" / didn't understand (before "it" short-followup — avoids "explain I didnt get it" → followup_blocked) ---
    if re.search(
        r"\b(didn'?t get it|dont get it|don'?t get it|still confused|not following|hard to follow|make it simpler|plain english|simpler terms|in simple terms)\b",
        s,
    ) or (re.match(r"^explain\b", s) and len(s) > 8):
        last_t = ctx.get("last_topic") or ""
        if last_t in (
            "blocked",
            "followup_blocked",
            "policy",
            "tool_analysis",
            "followup_tool_analysis",
            "overview",
            "followup_overview",
            "plain_explain",
            "safety_assessment",
        ):
            return "plain_explain"
        return "help_confused"

    # --- Product / co-pilot improvement feedback (not policy tuning) ---
    if re.search(r"\b(feature request|wish you could|you should add|make the (chat|co-pilot|copilot) better)\b", s) or (
        re.search(r"\bimprove\b", s)
        and not any(x in s for x in ("policy", "threshold", "rule", "yaml", "block rate", "false positive"))
    ):
        return "product_feedback"

    if any(w in s for w in ("that one", "the first", "the top", "this one")) or ("it" in words and len(s) < 40):
        return f"followup_{last}"
    if any(phrase in s for phrase in followup_phrases):
        return f"followup_{last}"

    # --- Questions starting with what / why / how / when / who / which ---
    if re.match(r"^(what\'s|whats|what|why|how\'s|how|when|who|which)\b", s):
        for keyword in tool_keywords:
            if keyword in s:
                return "tool_analysis"
        if any(w in s for w in ("block", "wrong", "happen", "issue", "problem", "risk", "danger")):
            return "blocked"
        if any(
            w in s
            for w in (
                "agentiva",
                "this",
                "product",
                "tool",
                "work",
                "do you do",
                "can you",
                "what can you",
            )
        ):
            return "capabilities"
        return "overview"

    # --- Frustration / confusion (after wh-questions so "what went wrong" → blocked) ---
    if any(
        w in s
        for w in (
            "confused",
            "don't understand",
            "dont understand",
            "doesnt work",
            "doesn't work",
            "not working",
            "broken",
            "bug",
            "error",
            "bad",
        )
    ) or (" wrong" in s and "what went wrong" not in s and "wrong with" not in s):
        return "help_confused"

    # --- Asking about specific agents / demos ---
    if any(w in s for w in ("demo-agent", "my agent", "support-agent", "agent-1", "agent 1")):
        return "agents"

    # --- Tool-specific mentions (after wh- and short follow-ups) ---
    for keyword, _db_pattern in tool_keywords.items():
        if keyword in s:
            return "tool_analysis"

    if any(w in s for w in ("what's the problem", "whats the problem", "any issues")):
        return "blocked"
    if "what should i worry about" in s:
        return "top_risks"

    # --- Greeting (after "no", "ok", etc.) ---
    if s in {"hi", "hello", "hey", "yo", "sup", "start", "help"} or (
        len(s) < 4 and s not in {"no", "ok", "yes", "nah"}
    ):
        return "greeting"
    if any(w in s for w in ("overview", "summary", "status", "give me a summary", "give me", "tell me", "show me", "dashboard", "report")):
        return "overview"
    if any(w in s for w in ("blocked", "block", "dangerous", "risky", "risk", "caught", "threat", "incident", "issue", "problem")):
        return "blocked"
    if any(w in s for w in ("hipaa", "health", "phi", "patient", "medical", "hippa")):
        return "hipaa"
    if any(w in s for w in ("soc2", "soc 2", "soc", "type ii", "type 2")):
        return "soc2"
    if any(w in s for w in ("pci", "payment", "credit card", "cardholder", "financial")):
        return "pci"
    if any(w in s for w in ("compliance", "compliant", "regulation", "gdpr", "eu ai act")):
        return "compliance_general"
    if any(w in s for w in ("agent", "which agent", "riskiest agent", "my agent", "agents")):
        return "agents"
    if any(w in s for w in ("policy", "policy hits", "rule", "threshold", "configure", "setting", "adjust", "too strict", "false positive", "fix")):
        return "policy"
    if any(w in s for w in ("what can you", "capabilities", "features", "help me", "what do you do")):
        return "capabilities"
    if any(w in s for w in ("thanks", "thank you", "thx", "great", "awesome", "perfect", "cool")):
        return "thanks"
    return "general"


async def generate_for_intent(intent: str, msg: str, data: Dict[str, Any], ctx: Dict[str, Any], db: Any = None) -> Dict[str, Any]:
    if intent == "tool_analysis":
        m = msg.lower()
        tool_pattern = None
        for keyword, pattern in tool_keywords.items():
            if keyword in m:
                tool_pattern = pattern
                break

        if tool_pattern:
            try:
                # Equivalent to: tool_name LIKE '{tool_pattern}' ORDER BY risk DESC LIMIT 5
                token = tool_pattern.strip("%").lower()
                rows = await list_actions(limit=500)
                matches = [r for r in rows if token in str(r.tool_name).lower()]
                matches = sorted(matches, key=lambda r: float(r.risk_score), reverse=True)[:5]

                if matches:
                    blocked_rows = [r for r in matches if str(r.decision).lower() == "block"]
                    shadowed_rows = [r for r in matches if str(r.decision).lower() == "shadow"]
                    allowed_rows = [r for r in matches if str(r.decision).lower() == "allow"]

                    top = matches[0]
                    tool_name = str(top.tool_name)
                    decision = str(top.decision).lower()
                    risk = float(top.risk_score)
                    args_str = str(top.arguments)[:150] if top.arguments else "no details"
                    agent = str(top.agent_id)

                    explanation = f"Here's what I found about **{tool_name}**:\n\n"
                    explanation += f"Total occurrences: {len(matches)} - "
                    parts: List[str] = []
                    if blocked_rows:
                        parts.append(f"{len(blocked_rows)} blocked")
                    if shadowed_rows:
                        parts.append(f"{len(shadowed_rows)} shadowed")
                    if allowed_rows:
                        parts.append(f"{len(allowed_rows)} allowed")
                    explanation += ", ".join(parts) + ".\n\n"

                    if decision == "block":
                        explanation += f"The most serious one was **blocked** at risk **{risk:.2f}** by agent **{agent}**. "
                        args_lower = args_str.lower()
                        reasons: List[str] = []
                        if any(w in args_lower for w in ["external", "evil", "outside", "@gmail", "@yahoo", "@hotmail"]):
                            reasons.append("the recipient is an external address")
                        if any(w in args_lower for w in ["ssn", "social security", "credit_card", "password", "secret"]):
                            reasons.append("sensitive data (PII/credentials) was detected in the content")
                        if any(w in args_lower for w in ["customer data", "patient", "medical", "financial"]):
                            reasons.append("it contained customer/patient data")
                        if any(w in args_lower for w in ["drop", "delete", "truncate", "rm -rf"]):
                            reasons.append("it contained a destructive operation")

                        if reasons:
                            explanation += "It was blocked because " + " and ".join(reasons) + "."
                        else:
                            explanation += "Multiple risk signals contributed to the high score."

                        explanation += f"\n\nArguments: `{args_str}`"
                        explanation += "\n\nThe action was intercepted before execution - no damage occurred."
                    else:
                        explanation += f"The highest-risk one had a score of **{risk:.2f}** and was **{decision}**."
                        explanation += f" It was from agent **{agent}**."

                    ctx["last_topic"] = "tool_analysis"
                    ctx.setdefault("last_data", {})
                    ctx["last_data"]["focus_tool"] = tool_name
                    ctx["last_data"]["focus_rows"] = [
                        {"tool": str(r.tool_name), "decision": str(r.decision), "risk": float(r.risk_score), "args": r.arguments, "agent": str(r.agent_id)}
                        for r in matches
                    ]

                    return {
                        "role": "assistant",
                        "content": explanation,
                        "suggestions": ["How to fix this?", "Adjust policy for this tool", "Show all blocked actions"],
                    }
                else:
                    return {
                        "role": "assistant",
                        "content": "I don't see any actions matching that tool in the audit log. The tool might not have been invoked yet, or it could be logged under a different name. Want me to show all recorded tools?",
                        "suggestions": ["Show all tools", "Session overview"],
                    }
            except Exception:
                pass

        return {
            "role": "assistant",
            "content": "I couldn't identify which tool you're asking about. Try being specific - like 'what happened with send_email?' or 'why was the database query blocked?'",
            "suggestions": ["What was blocked?", "Show all tools", "Session overview"],
        }
    if intent == "followup_tool_analysis":
        focus = ctx.get("last_data", {}).get("focus_rows", [])
        if focus:
            lines: List[str] = []
            for i, r in enumerate(focus):
                args_preview = str(r.get("args", ""))[:200]
                risk = float(r.get("risk", 0.0))
                lines.append(
                    f"**{i + 1}. {r['tool']}** — {r['decision']} at risk {risk:.2f}\n"
                    f"   Agent: {r['agent']}\n"
                    f"   Arguments: `{args_preview}`"
                )
            return {
                "role": "assistant",
                "content": f"Full details for all {len(focus)} occurrences:\n\n" + "\n\n".join(lines) + "\n\nWant me to suggest policy changes to handle these better?",
                "suggestions": ["Suggest policy fix", "Adjust threshold", "Export report"],
            }
        return {
            "role": "assistant",
            "content": "I don't have tool details in context yet. Ask about a specific tool first (for example \"problem with send email\").",
            "suggestions": ["Problem with send email", "Session overview", "What was blocked?"],
        }
    if intent in {"export", "export_menu", "followup_export"}:
        return {
            "role": "assistant",
            "content": (
                "Export from the dashboard (real audit data):\n\n"
                "1. Open **Audit log** in the sidebar.\n"
                "2. Optionally set a **date range** for PDFs.\n"
                "3. Use **Export SOC2 / HIPAA / PCI** for PDFs, or **Download JSON evidence** for structured SOC2/HIPAA/PCI bundles.\n\n"
                "API paths (same data): `/api/v1/compliance/soc2/evidence.json`, `/api/v1/compliance/hipaa/evidence.json`, "
                "`/api/v1/compliance/pci/evidence.json` (optional `?start=` and `end=` ISO dates)."
            ),
            "suggestions": ["What was blocked?", "HIPAA check", "Session overview"],
        }
    if intent in {"export_soc2", "export_hipaa", "export_pci", "export_all"}:
        label = {
            "export_soc2": "SOC2",
            "export_hipaa": "HIPAA",
            "export_pci": "PCI-DSS",
            "export_all": "all three",
        }[intent]
        return {
            "role": "assistant",
            "content": (
                f"To download **{label}** evidence: open **Dashboard → Audit log**, set your date range if needed, "
                "then use **Export … (PDF)** or **Export … evidence** (JSON). "
                f"Your current log has **{data['total']}** actions and **{data['blocked']}** blocks — exports use that data."
            ),
            "suggestions": ["Open Audit Log", "Session overview"],
        }

    _no_data_ok = {
        "greeting",
        "capabilities",
        "thanks",
        "general",
        "overview",
        "blocked",
        "followup_tool_analysis",
        "redirect",
        "setup",
        "help_confused",
        "export",
        "export_menu",
        "export_soc2",
        "export_hipaa",
        "export_pci",
        "export_all",
        "safety_assessment",
        "plain_explain",
        "product_feedback",
        # Compliance answers include regulatory citations (e.g. 45 CFR) even when the audit log is empty.
        "hipaa",
        "soc2",
        "compliance_general",
        "pci",
    }
    if not data["has_data"] and intent not in _no_data_ok and not intent.startswith("followup_"):
        return {
            "role": "assistant",
            "content": "I don't have audit data to analyze yet. Run your agent through Agentiva or load demo data, and I'll give you grounded security insight.",
            "suggestions": ["How to get started", "What can you do?"],
        }
    if intent == "redirect":
        return {
            "role": "assistant",
            "content": (
                "No worries! What else can I help with? I'm here to analyze your agent security, "
                "check compliance, or help tune policies."
            ),
            "suggestions": ["Session overview", "Compliance check", "Something else"],
        }
    if intent == "setup":
        return {
            "role": "assistant",
            "content": (
                "Getting started with Agentiva is quick:\n\n"
                "**1. Install:**\n"
                "`pipx install agentiva`\n\n"
                "**2. Add to your agent code:**\n"
                "```python\n"
                "from agentiva import Agentiva\n"
                "shield = Agentiva(mode='shadow')\n"
                "tools = shield.protect([your_tools])\n"
                "```\n\n"
                "**3. Start the server:**\n"
                "`agentiva serve --port 8000`\n\n"
                "Your dashboard will show all agent actions in real-time. Shadow mode means nothing gets blocked yet — "
                "you're just observing. When you're confident in the policies, switch to live mode.\n\n"
                "Need help with a specific framework like LangChain or CrewAI?"
            ),
            "suggestions": ["LangChain setup", "CrewAI setup", "MCP proxy setup"],
        }
    if intent == "help_confused":
        return {
            "role": "assistant",
            "content": (
                "Let me help! I'm Agentiva's security co-pilot. Here's what I can do:\n\n"
                "**Ask me about your agents:** 'what happened today?' or 'show me blocked actions'\n"
                "**Check compliance:** 'HIPAA-aligned check' or 'SOC2 gap analysis'\n"
                "**Get specific:** 'why was send_email blocked?' or 'what's wrong with the database calls?'\n"
                "**Tune policies:** 'too many blocks' or 'suggest policy changes'\n\n"
                "If something was unclear, say **'explain in plain English'** right after I answer — I'll simplify.\n\n"
                "What's on your mind?"
            ),
            "suggestions": ["Session overview", "What was blocked?", "Explain last answer in plain English"],
        }
    if intent == "plain_explain":
        focus = ctx.get("last_data", {}).get("focus_blocked") or data.get("top_blocked") or []
        if not focus:
            return {
                "role": "assistant",
                "content": (
                    "I can put it more simply — first ask **“what was blocked?”** so I know which action you mean. "
                    "Then say **“explain in plain English”** and I'll break down that block in everyday language."
                ),
                "suggestions": ["What was blocked?", "Session overview", "Help me get started"],
            }
        body = _plain_explain_blocked(focus[0])
        return {
            "role": "assistant",
            "content": body
            + "\n\nIf you want the technical view again, ask **“why was #1 blocked?”** or check the **Audit log** for the full payload.",
            "suggestions": ["Why was #1 blocked?", "How to allow safely?", "Session overview"],
        }
    if intent == "product_feedback":
        return {
            "role": "assistant",
            "content": (
                "Thanks for speaking up - that's how we make the co-pilot better for everyone. "
                "We keep tightening **intent detection** (so phrases like 'explain that again' hit the right answer) "
                "and **plain-language explanations** grounded in your audit log.\n\n"
                "For a specific idea or bug, open an issue on **GitHub** so it can be tracked; "
                "for one-off confusion, tell me what you expected right after an answer and I'll adapt in-thread."
            ),
            "suggestions": ["What was blocked?", "Explain in plain English", "Session overview"],
        }
    if intent == "greeting":
        if not data["has_data"]:
            return {
                "role": "assistant",
                "content": (
                    "Hey! I'm your Agentiva security co-pilot. I don't see any actions in the audit log yet — "
                    "once something runs, I'll tell you what was blocked, shadowed, or allowed. "
                    "Want to run the demo or connect an agent first?"
                ),
                "suggestions": ["Run demo", "Register an agent", "How do I set this up?"],
            }
        greetings = [
            f"Hey there! I'm your security co-pilot, watching over your agents. You've got {data['total']} actions logged — {data['blocked']} blocked and {data['shadowed']} under review. Want a quick breakdown?",
            f"Hi! I'm your Agentiva co-pilot — I can see {data['total']} intercepted actions so far and a {data['block_rate']}% block rate. What should we look at first?",
            f"Hello! I'm your security co-pilot. I see activity from {len(data['agents'])} agent(s). Want overview, incidents, or compliance?",
        ]
        return {"role": "assistant", "content": random.choice(greetings), "suggestions": ["Session overview", "Any security issues?", "HIPAA compliance check"]}
    if intent == "overview":
        rate_note = (
            "That's a high block rate — likely either noisy agent behavior or strict policy rules."
            if data["block_rate"] > 40
            else "That block rate looks healthy."
        )
        top = data["top_blocked"][0] if data["top_blocked"] else None
        top_note = f" Top blocked action: `{top['tool']}` from `{top['agent']}` at risk {top['risk']:.2f}." if top else ""
        return {
            "role": "assistant",
            "content": (
                f"Here's the current picture: {data['total']} actions total — {data['blocked']} blocked, "
                f"{data['shadowed']} shadowed, and {data['allowed']} allowed. That's a {data['block_rate']}% block rate. "
                f"{rate_note}{top_note} Want me to dig into what triggered those blocks?"
            ),
            "suggestions": ["Show me the blocked actions", "Which agent needs attention?", "Export compliance report"],
        }
    _detail_kw = (
        "show full details",
        "full details",
        "show details",
        "more details",
        "all details",
        "elaborate",
        "tell me more",
        "dig deeper",
    )
    if intent == "followup_overview":
        mlow = msg.lower()
        if any(k in mlow for k in _detail_kw):
            agents = data.get("agents", [])
            ag_lines = ", ".join(f"{a['id']} ({a['count']})" for a in agents[:12]) or "none recorded"
            return {
                "role": "assistant",
                "content": (
                    "**Expanded session summary**\n\n"
                    f"- Total actions: **{data['total']}**\n"
                    f"- Blocked: **{data['blocked']}** · Shadowed: **{data['shadowed']}** · Allowed: **{data['allowed']}**\n"
                    f"- Block rate: **{data['block_rate']}%**\n\n"
                    f"Agents by activity: {ag_lines}\n\n"
                    "Say **what was blocked?** for the ranked list, then **show full details** again for full argument payloads."
                ),
                "suggestions": ["What was blocked?", "Export compliance report", "HIPAA check"],
            }
        rate_note = (
            "That's a high block rate — likely either noisy agent behavior or strict policy rules."
            if data["block_rate"] > 40
            else "That block rate looks healthy."
        )
        top = data["top_blocked"][0] if data["top_blocked"] else None
        top_note = f" Top blocked action: `{top['tool']}` from `{top['agent']}` at risk {top['risk']:.2f}." if top else ""
        return {
            "role": "assistant",
            "content": (
                f"Here's the picture again: {data['total']} actions total — {data['blocked']} blocked, "
                f"{data['shadowed']} shadowed, and {data['allowed']} allowed ({data['block_rate']}% block rate). "
                f"{rate_note}{top_note} Say **show full details** for a fuller breakdown."
            ),
            "suggestions": ["Show full details", "What was blocked?", "Export compliance report"],
        }
    if intent == "blocked":
        top = data["top_blocked"]
        if not top:
            return {"role": "assistant", "content": "Good news — no blocked actions in the current data. Want me to review shadowed actions instead?", "suggestions": ["View shadowed actions", "Session overview"]}
        agent_block_counts = data.get("agent_block_counts") or {}
        cred_shadow = data.get("credential_shadow_by_agent") or {}
        lines = []
        for i, b in enumerate(top[:5], start=1):
            path_note = ""
            p = b.get("path") or _action_path_from_args(b.get("args"))
            if p:
                path_note = f" · file `{p}`"
            lines.append(f"{i}. `{b['tool']}` by `{b['agent']}` at risk {b['risk']:.2f}{path_note}")
        first = top[0]
        agent = str(first.get("agent") or "")
        n_agent_blocks = int(agent_block_counts.get(agent, len(top)))
        path = first.get("path") or _action_path_from_args(first.get("args"))
        desc = _describe_blocked_tool(str(first.get("tool")), first.get("args"))
        risk = float(first.get("risk") or 0.0)
        path_seg = f"{path} " if path else ""
        lead = (
            f"{agent} had {n_agent_blocks} blocked action{'s' if n_agent_blocks != 1 else ''}: "
            f"{path_seg}{desc} at risk {risk:.2f}."
        )
        cred_n = int(cred_shadow.get(agent, 0))
        if cred_n > 0:
            lead += f" {cred_n} warning(s) for hardcoded credentials in scanned files."
        ctx.setdefault("last_data", {})["focus_blocked"] = top
        return {
            "role": "assistant",
            "content": lead + "\n\n" + "I found blocked actions worth reviewing:\n\n" + "\n".join(lines) + "\n\nAll were intercepted before execution. Want me to explain the top one?",
            "suggestions": ["Why was #1 blocked?", "Show full details", "Export audit report"],
        }
    if intent == "followup_blocked":
        mlow = msg.lower()
        if any(k in mlow for k in _detail_kw):
            focus = ctx.get("last_data", {}).get("focus_blocked") or data.get("top_blocked") or []
            if focus:
                lines2: List[str] = []
                for i, b in enumerate(focus[:10], 1):
                    args = b.get("args")
                    if isinstance(args, dict):
                        args_str = json.dumps(args, default=str)[:800]
                    else:
                        args_str = str(args)[:800]
                    lines2.append(
                        f"**{i}. `{b['tool']}`** — agent `{b['agent']}`, risk **{float(b['risk']):.2f}**\n"
                        f"Arguments: `{args_str}`"
                    )
                return {
                    "role": "assistant",
                    "content": (
                        "Here is the full detail for each blocked action in context:\n\n"
                        + "\n\n".join(lines2)
                        + "\n\nFor PDF exports, open **Dashboard → Audit log** and use **Export SOC2 / HIPAA / PCI** (or JSON evidence downloads)."
                    ),
                    "suggestions": ["Suggest policy fix", "Session overview", "Export compliance report"],
                }
        focus = ctx.get("last_data", {}).get("focus_blocked") or data["top_blocked"]
        if not focus:
            return {"role": "assistant", "content": "I can explain it, but I need a blocked action in context first. Ask 'what was blocked?' and I'll drill in.", "suggestions": ["Show blocked actions", "Session overview"]}
        top = focus[0]
        hint = _arg_hint(top.get("args"))
        path = top.get("path") or _action_path_from_args(top.get("args"))
        path_note = f" File: `{path}`." if path else ""
        return {
            "role": "assistant",
            "content": (
                f"That top item was `{top['tool']}` from `{top['agent']}` with risk {top['risk']:.2f}.{path_note} "
                "It likely combined tool sensitivity with content/target risk signals. "
                f"I can see `{hint}` in the request payload, which helps explain why it was treated as high-risk. "
                "Say **show full details** to see every blocked row with full arguments."
            ),
            "suggestions": ["Show full details", "How to allow this safely?", "Adjust policy"],
        }
    if intent == "shadowed":
        top = data.get("top_shadowed") or []
        if not top:
            return {
                "role": "assistant",
                "content": "I don't see any shadowed actions in the current data.",
                "suggestions": ["Session overview", "Compliance check"],
            }
        lines = []
        for i, b in enumerate(top[:5], start=1):
            lines.append(f"{i}. `{b['tool']}` by `{b['agent']}` at risk {b['risk']:.2f}")
        ctx.setdefault("last_data", {})["focus_shadowed"] = top
        return {
            "role": "assistant",
            "content": "Here are the most recent shadowed actions (observed, not executed):\n\n" + "\n".join(lines) + "\n\nWant full arguments for each one?",
            "suggestions": ["Show full details", "Allow this one", "Session overview"],
        }
    if intent == "followup_shadowed":
        mlow = msg.lower()
        if any(k in mlow for k in _detail_kw):
            focus = ctx.get("last_data", {}).get("focus_shadowed") or data.get("top_shadowed") or []
            if focus:
                lines2: List[str] = []
                for i, b in enumerate(focus[:10], 1):
                    args = b.get("args")
                    if isinstance(args, dict):
                        args_str = json.dumps(args, default=str)[:800]
                    else:
                        args_str = str(args)[:800]
                    lines2.append(
                        f"**{i}. `{b['tool']}`** — agent `{b['agent']}`, risk **{float(b['risk']):.2f}**\n"
                        f"Arguments: `{args_str}`"
                    )
                return {
                    "role": "assistant",
                    "content": "Full details for recent shadowed actions:\n\n" + "\n\n".join(lines2),
                    "suggestions": ["Allow this one", "Session overview", "Compliance check"],
                }
        return {
            "role": "assistant",
            "content": "Say **show full details** to see the full argument payloads for the shadowed actions.",
            "suggestions": ["Show full details", "Allow this one", "Session overview"],
        }
    if intent in {"hipaa", "followup_hipaa"}:
        return {
            "role": "assistant",
            "content": (
                f"From an **HIPAA-aligned** perspective: {data['total']} actions logged and {data['blocked']} high-risk attempts blocked. "
                "That supports evidence for 45 CFR § 164.312(a)(1) access controls, § 164.312(b) audit controls, and § 164.312(e)(1) transmission safeguards. "
                "Formal HIPAA certification still requires a qualified assessor."
            ),
            "suggestions": ["Export HIPAA report", "Show PHI access attempts", "SOC2 check"],
        }
    if intent in {"soc2", "followup_soc2", "compliance_general", "followup_compliance_general"}:
        return {
            "role": "assistant",
            "content": (
                f"**SOC2-ready** evidence: {data['total']} actions evaluated with {data['blocked']} blocked before execution, "
                "plus full audit traceability — a solid shape for CC6/CC7 discussions with your auditor."
            ),
            "suggestions": ["Export SOC2 report", "HIPAA check", "Show evidence for CC7.1"],
        }
    if intent in {"pci", "followup_pci"}:
        return {
            "role": "assistant",
            "content": (
                f"**PCI-DSS aligned** view: {data['blocked']} risky actions blocked and "
                f"{data['total']} actions logged for review — a solid baseline for Req 7/10-style evidence. "
                "PCI formal certification is still vendor/assessor-specific."
            ),
            "suggestions": ["Export PCI report", "Show financial actions", "HIPAA check"],
        }
    if intent == "agents":
        if not data["agents"]:
            return {"role": "assistant", "content": "I don't see any active agents in the current audit data yet.", "suggestions": ["How to register", "Run demo"]}
        rows = ", ".join(f"{a['id']} ({a['count']})" for a in data["agents"][:6])
        return {"role": "assistant", "content": f"Active agents by activity: {rows}. Want me to call out the riskiest one?", "suggestions": ["Which is riskiest?", "Show blocked by agent", "Session overview"]}
    if intent in {"policy", "followup_policy"}:
        top = data["top_blocked"]
        if top:
            first = top[0]
            tool = first["tool"]
            agent = first["agent"]
            risk = first["risk"]
            hint = _arg_hint(first.get("args"))
            ext = ""
            if isinstance(first.get("args"), dict):
                to = str(first["args"].get("to", "")).strip()
                if to:
                    ext = f" (sending to {to})"
            likely = (
                "block_external_email"
                if "email" in tool.lower()
                else "block_destructive_sql"
                if "database" in tool.lower() or "sql" in tool.lower()
                else "block_sensitive_data"
            )
            detail = f"{tool} blocked at risk {risk:.2f}"
            if hint:
                detail += f" with {hint}"
            detail += ext
            return {
                "role": "assistant",
                "content": (
                    "Based on the blocked actions, here's what triggered:\n\n"
                    f"1. **{detail}** — likely triggered by **{likely}**.\n\n"
                    "Your policies caught dangerous behavior while allowing lower-risk activity through. "
                    "Want me to suggest adjustments or keep this strict?\n\n"
                    "**Where to edit:** `policies/default.yaml` (restart the API), or the dashboard **Policies** page."
                ),
                "suggestions": ["Show policy trigger", "Suggest policy changes", "Keep current policy"],
            }
        return {
            "role": "assistant",
            "content": (
                f"With a {data['block_rate']}% block rate, I'd start by reviewing top blocked actions for false positives before changing thresholds globally. "
                "If you want, I can propose targeted policy adjustments.\n\n"
                "**Where to edit:** `policies/default.yaml` (restart the API), or the dashboard **Policies** page."
            ),
            "suggestions": ["Show false positives", "Suggest policy changes", "Generate custom rule"],
        }
    if intent in {"capabilities", "followup_capabilities"}:
        return {
            "role": "assistant",
            "content": (
                "I can summarize activity, explain why actions were blocked, map behavior to compliance controls, "
                "and suggest policy tuning — all from your actual audit data."
            ),
            "suggestions": ["Session overview", "Security check", "HIPAA compliance"],
        }
    if intent in {"thanks", "followup_thanks"}:
        return {"role": "assistant", "content": random.choice(["Happy to help.", "Anytime — I’ll keep monitoring.", "Glad that helped."]), "suggestions": ["Session overview", "Any new issues?"]}
    if intent == "safety_assessment":
        block_rate = data.get("block_rate", 0)
        total = data.get("total", 0)
        blocked = data.get("blocked", 0)
        if not data["has_data"]:
            assessment = (
                "I don't have enough data to assess safety yet. Run your agent in shadow mode for a few hours, then ask me again."
            )
        elif block_rate > 50:
            assessment = (
                f"I'd hold off on going live. Your block rate is {block_rate}% — that's high. Either your agent is attempting "
                "a lot of risky actions, or your policies need tuning. Let me help you review the blocked actions first."
            )
        elif block_rate > 20:
            assessment = (
                f"Getting closer. Block rate is {block_rate}% with {blocked} incidents caught. I'd recommend reviewing each "
                "blocked action to confirm they're genuine threats, not false positives. Once you've verified, you can switch "
                "to live mode with confidence."
            )
        elif block_rate > 5:
            assessment = (
                f"Looking good. Block rate is just {block_rate}% — your agent is mostly behaving well and the few blocks look "
                "like genuine threats. I'd feel comfortable moving to live mode, but keep shadow mode on for any new tools you add."
            )
        else:
            assessment = (
                f"Your agent looks clean — only {block_rate}% block rate across {total} actions. The policies are catching edge "
                "cases without over-blocking. Safe to go live."
            )
        return {
            "role": "assistant",
            "content": assessment,
            "suggestions": ["Show blocked actions", "Switch to live mode", "Export compliance report"],
        }
    if intent == "top_risks":
        top = data["top_blocked"][:3]
        if not top:
            return {"role": "assistant", "content": "No major risk spikes right now.", "suggestions": ["Session overview", "Any issues?"]}
        rows = ", ".join(f"{t['tool']} ({t['risk']:.2f})" for t in top)
        return {"role": "assistant", "content": f"Top risks right now: {rows}. Want me to drill into one?", "suggestions": ["Analyze top tool", "Policy suggestions"]}

    if intent == "allow_one":
        return {
            "role": "assistant",
            "content": (
                "To do a **one-off allow** (shadow → allow) for the most recent shadowed/blocked action:\n"
                "- Trigger the action once (so it is in the audit DB)\n"
                "- Ask: **allow this one** (or **allow for shadow**)\n"
                "- Reply: **Confirm** to apply the narrow rule\n\n"
                "Broader changes: edit **`policies/default.yaml`** in the repo and restart the API, or use the dashboard **Policies** page.\n\n"
                "If this message appears instead of a YAML snippet, ensure the dashboard talks to the same API process that logged the action."
            ),
            "suggestions": ["Allow this one", "Confirm", "What was blocked?"],
        }

    if intent.startswith("followup_") and intent not in (
        "followup_blocked",
        "followup_overview",
        "followup_tool_analysis",
    ):
        last_t = ctx.get("last_topic") or ""
        if last_t == "hipaa":
            return await generate_for_intent("hipaa", msg, data, ctx, db)
        if last_t == "soc2":
            return await generate_for_intent("soc2", msg, data, ctx, db)
        if last_t == "greeting":
            return await generate_for_intent("overview", msg, data, ctx, db)
        if last_t == "safety_assessment":
            return await generate_for_intent("blocked", msg, data, ctx, db)
        if last_t == "pci":
            return await generate_for_intent("pci", msg, data, ctx, db)
        return await generate_for_intent("overview", msg, data, ctx, db)

    if intent == "general":
        return {
            "role": "assistant",
            "content": (
                "I'm not sure I caught that — I can help with security analysis, compliance checks, and policy tuning. "
                "Try: 'give me a summary', 'what was blocked?', or 'is my agent safe for production?'. "
                "For **what to change in the repo**, policy rules live in **`policies/default.yaml`**; restart the API after edits."
            ),
            "suggestions": ["Session overview", "What was blocked?", "Compliance check"],
        }
    return {
        "role": "assistant",
        "content": "I can help with security analysis, compliance checks, and policy tuning. Try: 'give me a summary' or 'what was blocked?'.",
        "suggestions": ["Session overview", "What was blocked?", "Compliance check"],
    }


async def generate_response(msg: str, db: Any, session_id: str = "", history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Generate a natural, contextual, data-grounded response."""
    m = msg.lower().strip()
    if not m:
        return {
            "role": "assistant",
            "content": "Ask me anything about intercepted actions, blocks, risk, or agents.",
            "suggestions": ["Session overview", "What was blocked?", "Compliance check"],
        }
    ctx = session_context.get(session_id, {"last_topic": None, "last_data": {}, "message_count": 0})
    ctx["message_count"] = ctx.get("message_count", 0) + 1
    data = await fetch_audit_data(db)
    intent = classify_intent(m, ctx)
    response = await generate_for_intent(intent, m, data, ctx, db)
    if not intent.startswith("followup_") and intent not in ("plain_explain",):
        ctx["last_topic"] = intent
    if "last_data" not in ctx:
        ctx["last_data"] = {}
    session_context[session_id] = ctx
    return response


@router.post("/sessions")
async def create_session() -> Dict[str, Any]:
    try:
        row = await create_chat_session(tenant_id="default", title="New conversation")
        return {
            "id": row.id,
            "title": row.title,
            "tenant_id": row.tenant_id,
            "created_at": row.created_at.isoformat(),
        }
    except Exception:
        session_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        chat_sessions[session_id] = {
            "id": session_id,
            "title": "New conversation",
            "created_at": now,
            "updated_at": now,
        }
        chat_messages[session_id] = []
        return {"id": session_id, "title": "New conversation"}


@router.get("/sessions")
async def list_sessions() -> List[Dict[str, Any]]:
    try:
        rows = await list_chat_sessions(tenant_id="default")
        return [
            {
                "id": r.id,
                "title": r.title,
                "tenant_id": r.tenant_id,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    except Exception:
        return list(chat_sessions.values())


@router.delete("/sessions/all")
async def delete_all_sessions() -> Dict[str, Any]:
    deleted = len(chat_sessions)
    chat_sessions.clear()
    chat_messages.clear()
    return {"deleted": True, "deleted_sessions": deleted}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    try:
        ok = await delete_chat_session(session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception:
        chat_sessions.pop(session_id, None)
        chat_messages.pop(session_id, None)
        return {"deleted": True}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, payload: ChatMessageRequest) -> Dict[str, Any]:
    user_msg = payload.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    history: Optional[List[Dict[str, str]]] = None
    try:
        sess = await get_chat_session(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found")
        prior_msgs = await list_chat_messages(session_id)
        history = [{"role": m.role, "content": m.content} for m in prior_msgs[-5:]]
        await add_chat_message(session_id, "user", user_msg)
        if sess.title in ("", "New chat", "New conversation"):
            await update_chat_session_title(session_id, user_msg[:80] + ("…" if len(user_msg) > 80 else ""))
    except HTTPException:
        raise
    except Exception:
        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                "id": session_id,
                "title": "New conversation",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        prior = list(chat_messages.get(session_id, []))
        history = [{"role": m["role"], "content": m["content"]} for m in prior[-5:]]
        chat_messages.setdefault(session_id, []).append({"role": "user", "content": user_msg})
        if chat_sessions[session_id]["title"] == "New conversation":
            chat_sessions[session_id]["title"] = user_msg[:80]

    response = await generate_response(user_msg, db=None, session_id=session_id, history=history)
    response["answer"] = response["content"]

    try:
        await add_chat_message(session_id, "assistant", response["content"])
    except Exception:
        chat_messages.setdefault(session_id, []).append({"role": "assistant", "content": response["content"]})
    return response


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> Dict[str, Any]:
    try:
        sess = await get_chat_session(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found")
        msgs = await list_chat_messages(session_id)
        return {
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in msgs
            ],
        }
    except HTTPException:
        raise
    except Exception:
        return {"session_id": session_id, "messages": chat_messages.get(session_id, [])}
