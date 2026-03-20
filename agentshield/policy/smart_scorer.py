from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple
import fnmatch
import re


@dataclass
class RiskAssessment:
    score: float
    signals: List[str] = field(default_factory=list)
    recommendation: str = "shadow"
    explanation: str = ""


class SmartRiskScorer:
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        enable_llm_judge: bool = False,
        llm_client: Any = None,
    ) -> None:
        self.weights = {
            "tool_sensitivity": 1.0,
            "recipient_analysis": 1.0,
            "content_analysis": 1.0,
            "pattern_detection": 1.0,
            "time_analysis": 1.0,
            "agent_reputation": 1.0,
            "frequency": 1.0,
            "data_sensitivity": 1.0,
        }
        if weights:
            self.weights.update(weights)
        self.enable_llm_judge = enable_llm_judge
        self.llm_client = llm_client
        self._agent_action_counts: Dict[str, int] = {}
        self._whitelists: Dict[str, Any] = {}

    def configure_policy_context(self, *, whitelists: Optional[Dict[str, Any]] = None) -> None:
        self._whitelists = whitelists or {}

    def score_action(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        agent_role: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        recent_actions_per_minute: int = 1,
        bulk_size: int = 1,
        agent_reputation: str = "established",
        first_time_tool: bool = False,
        data_classification: str = "none",
    ) -> RiskAssessment:
        ts = timestamp or datetime.now(UTC)
        score_components: List[Tuple[str, float, str]] = []

        tool_score, tool_signal = self._tool_sensitivity(tool_name)
        score_components.append(("tool_sensitivity", tool_score, tool_signal))

        recipient_score, recipient_signal = self._recipient_analysis(arguments)
        score_components.append(("recipient_analysis", recipient_score, recipient_signal))

        pattern_score, pattern_signal = self._pattern_detection(
            first_time_tool=first_time_tool,
            bulk_size=bulk_size,
            recent_actions_per_minute=recent_actions_per_minute,
        )
        score_components.append(("pattern_detection", pattern_score, pattern_signal))

        time_score, time_signal = self._time_analysis(ts)
        score_components.append(("time_analysis", time_score, time_signal))

        reputation_score, reputation_signal = self._agent_reputation(agent_reputation)
        score_components.append(("agent_reputation", reputation_score, reputation_signal))

        content_score, content_signal = self._content_analysis(arguments)
        score_components.append(("content_analysis", content_score, content_signal))

        frequency_score, frequency_signal = self._frequency(agent_id, recent_actions_per_minute)
        score_components.append(("frequency", frequency_score, frequency_signal))

        data_score, data_signal = self._data_sensitivity(data_classification)
        score_components.append(("data_sensitivity", data_score, data_signal))

        weighted = 0.0
        signals: List[str] = []
        for key, value, signal in score_components:
            weighted += self.weights[key] * value
            if signal:
                signals.append(signal)

        score = max(0.0, min(1.0, round(weighted, 4)))

        # Context-aware adjustments (self-access, authorized roles, known support context).
        ctx = context or {}
        ctx_adjust = 0.0
        if not ctx:
            ctx_adjust += 0.15
        else:
            requested_by = str(ctx.get("requested_by", "")).lower()
            customer_id_match = ctx.get("customer_id_match")
            user_role = str(ctx.get("user_role", "")).lower()
            session_type = str(ctx.get("session_type", "")).lower()

            if requested_by == "customer" and customer_id_match is True:
                ctx_adjust -= 0.15
            if session_type == "support_ticket":
                ctx_adjust -= 0.05
            if customer_id_match is False:
                ctx_adjust += 0.2

            if user_role == "doctor":
                fields = arguments.get("fields", [])
                if isinstance(fields, list):
                    fields_str = " ".join(str(x).lower() for x in fields)
                else:
                    fields_str = str(fields).lower()
                if "medical" in fields_str or "medical_history" in fields_str:
                    ctx_adjust -= 0.1

            # Minimal role-aware reduction for sales agents emailing externally.
            if agent_role == "sales_agent" and tool_name == "send_email":
                to = str(arguments.get("to", ""))
                if "@yourcompany.com" not in to:
                    ctx_adjust -= 0.1

        if ctx_adjust != 0.0:
            score = max(0.0, min(1.0, round(score + ctx_adjust, 4)))

        # Whitelist-based risk reduction/increase (trusted domains/endpoints, safe shell commands).
        wl_adjust = 0.0
        if self._whitelists:
            tool_lower = tool_name.lower()
            args = arguments or {}

            trusted_domains = self._whitelists.get("trusted_domains") or []
            trusted_email_domains = self._whitelists.get("trusted_email_domains") or []
            safe_shell_commands = self._whitelists.get("safe_shell_commands") or []

            if "call_external_api" in tool_lower:
                url = str(args.get("url", "") or "")
                domain = ""
                m = re.search(r"^https?://([^/]+)", url)
                if m:
                    domain = m.group(1)
                if domain:
                    if any(fnmatch.fnmatch(domain, p) for p in trusted_domains):
                        wl_adjust -= 0.15
                    else:
                        wl_adjust += 0.15

            if "send_email" in tool_lower:
                to = str(args.get("to", "") or "")
                if to:
                    if any(fnmatch.fnmatch(to, p) for p in trusted_email_domains):
                        wl_adjust -= 0.05

            if "run_shell_command" in tool_lower:
                cmd = str(args.get("command", "") or "")
                if cmd and safe_shell_commands:
                    if any(fnmatch.fnmatch(cmd, pat) for pat in safe_shell_commands):
                        wl_adjust -= 0.1
                    else:
                        wl_adjust += 0.1

        if wl_adjust != 0.0:
            score = max(0.0, min(1.0, round(score + wl_adjust, 4)))

        recommendation = self._recommend(score)
        explanation = (
            f"Risk score {score:.2f} based on {len(signals)} active signal(s)."
            + (f" context_adjust={ctx_adjust:+.2f}" if ctx_adjust != 0.0 else "")
        )

        if self.enable_llm_judge and self.llm_client:
            llm_signal = self._llm_judge(tool_name, arguments, score)
            if llm_signal:
                signals.append(llm_signal)
                explanation = f"{explanation} LLM judge refinement applied."

        return RiskAssessment(
            score=score,
            signals=signals,
            recommendation=recommendation,
            explanation=explanation,
        )

    def _tool_sensitivity(self, tool_name: str) -> Tuple[float, str]:
        lower = tool_name.lower()
        if "email" in lower or "gmail" in lower:
            return 0.7, "tool_sensitivity=email(+0.7)"
        if "database" in lower:
            return 0.6, "tool_sensitivity=database(+0.6)"
        if "slack" in lower:
            return 0.4, "tool_sensitivity=slack(+0.4)"
        if "jira" in lower:
            return 0.3, "tool_sensitivity=jira(+0.3)"
        return 0.2, "tool_sensitivity=default(+0.2)"

    def _recipient_analysis(self, arguments: Dict[str, Any]) -> Tuple[float, str]:
        recipient = str(arguments.get("to", arguments.get("recipient", "")))
        if recipient and "@" in recipient and "@yourcompany.com" not in recipient:
            return 0.3, "recipient_analysis=external(+0.3)"
        if str(arguments.get("channel", "")).startswith("#"):
            return 0.2, "recipient_analysis=broadcast(+0.2)"
        return 0.0, "recipient_analysis=internal(+0.0)"

    def _pattern_detection(
        self, first_time_tool: bool, bulk_size: int, recent_actions_per_minute: int
    ) -> Tuple[float, str]:
        score = 0.0
        notes: List[str] = []
        if first_time_tool:
            score += 0.1
            notes.append("first_time_tool(+0.1)")
        if bulk_size >= 10:
            score += 0.3
            notes.append("bulk_operation(+0.3)")
        if recent_actions_per_minute >= 60:
            score += 0.2
            notes.append("rapid_fire(+0.2)")
        return score, f"pattern_detection={','.join(notes)}" if notes else ""

    def _time_analysis(self, timestamp: datetime) -> Tuple[float, str]:
        weekday = timestamp.weekday()
        hour = timestamp.hour
        if weekday >= 5:
            return 0.15, "time_analysis=weekend(+0.15)"
        if hour < 8 or hour > 19:
            return 0.1, "time_analysis=after_hours(+0.1)"
        return 0.0, "time_analysis=business_hours(+0.0)"

    def _agent_reputation(self, reputation: str) -> Tuple[float, str]:
        if reputation == "new":
            return -0.1, "agent_reputation=new(-0.1 safer threshold)"
        if reputation == "trusted":
            return 0.0, "agent_reputation=established(+0.0)"
        if reputation == "unknown":
            return 0.2, "agent_reputation=unknown(+0.2)"
        return 0.0, "agent_reputation=established(+0.0)"

    def _content_analysis(self, arguments: Dict[str, Any]) -> Tuple[float, str]:
        blob = str(arguments).lower()
        destructive = ["delete", "drop", "remove", "destroy", "truncate"]
        sensitive = ["password", "secret", "token", "credential", "confidential"]
        score = 0.0
        notes: List[str] = []
        if any(term in blob for term in destructive):
            score += 0.4
            notes.append("destructive_keywords(+0.4)")
        if any(term in blob for term in sensitive):
            score += 0.3
            notes.append("sensitive_data(+0.3)")
        return score, f"content_analysis={','.join(notes)}" if notes else "content_analysis=normal(+0.0)"

    def _frequency(self, agent_id: str, recent_actions_per_minute: int) -> Tuple[float, str]:
        self._agent_action_counts[agent_id] = self._agent_action_counts.get(agent_id, 0) + 1
        if recent_actions_per_minute >= 100:
            return 0.3, "frequency=abnormal(+0.3)"
        if recent_actions_per_minute >= 40:
            return 0.1, "frequency=high(+0.1)"
        return 0.0, "frequency=normal(+0.0)"

    def _data_sensitivity(self, data_classification: str) -> Tuple[float, str]:
        cls = data_classification.lower()
        if cls == "credentials":
            return 0.5, "data_sensitivity=credentials(+0.5)"
        if cls == "financial":
            return 0.4, "data_sensitivity=financial(+0.4)"
        if cls == "pii":
            return 0.3, "data_sensitivity=pii(+0.3)"
        return 0.0, "data_sensitivity=none(+0.0)"

    def _recommend(self, score: float) -> str:
        if score >= 0.8:
            return "block"
        if score >= 0.6:
            return "approve"
        if score >= 0.35:
            return "shadow"
        return "allow"

    def _llm_judge(self, tool_name: str, arguments: Dict[str, Any], score: float) -> str:
        # Opt-in extension point: call external provider if wired by enterprise users.
        _ = (tool_name, arguments, score)
        return "LLM judge enabled (no-op in local deterministic mode)"
