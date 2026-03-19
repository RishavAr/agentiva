from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class SimulationResult:
    action_id: str
    tool_name: str
    impact: List[str] = field(default_factory=list)
    reversible: bool = True
    risk_assessment: str = "low"
    estimated_side_effects: List[str] = field(default_factory=list)


SimulatorHandler = Callable[[str, Dict[str, Any], str], SimulationResult]


class ActionSimulator:
    def __init__(self) -> None:
        self._handlers: Dict[str, SimulatorHandler] = {}
        self._register_builtin_simulators()

    def register(self, tool_name: str) -> Callable[[SimulatorHandler], SimulatorHandler]:
        def decorator(func: SimulatorHandler) -> SimulatorHandler:
            self._handlers[tool_name] = func
            return func

        return decorator

    def simulate(self, action_id: str, tool_name: str, arguments: Dict[str, Any]) -> SimulationResult:
        handler = self._handlers.get(tool_name, self._simulate_generic_api)
        return handler(action_id, arguments or {}, tool_name)

    def _register_builtin_simulators(self) -> None:
        self._handlers["gmail_send"] = self._simulate_gmail_send
        self._handlers["send_email"] = self._simulate_gmail_send
        self._handlers["slack_post"] = self._simulate_slack_post
        self._handlers["jira_update"] = self._simulate_jira_update
        self._handlers["database_query"] = self._simulate_database_query
        self._handlers["database_write"] = self._simulate_database_query
        self._handlers["generic_api"] = self._simulate_generic_api

    def _simulate_gmail_send(
        self, action_id: str, arguments: Dict[str, Any], tool_name: str
    ) -> SimulationResult:
        to = str(arguments.get("to", "unknown"))
        subject = str(arguments.get("subject", "(no subject)"))
        external = "@yourcompany.com" not in to
        attachments = bool(arguments.get("attachments"))
        estimated_visibility = int(arguments.get("thread_participants", 1))
        impact = [
            f"+ Would send email to: {to}",
            f"~ Subject: {subject}",
            f"~ Contains attachments: {'yes' if attachments else 'no'}",
            f"~ Estimated visibility: {estimated_visibility} people in thread",
        ]
        if not attachments:
            impact.append("- No attachment")
        side_effects = ["Recipient receives message immediately.", "Potential compliance trail created."]
        risk = "medium"
        if external:
            impact.append("! WARNING: External recipient detected")
            side_effects.append("Possible data exfiltration risk.")
            risk = "high"
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=impact,
            reversible=False,
            risk_assessment=risk,
            estimated_side_effects=side_effects,
        )

    def _simulate_slack_post(
        self, action_id: str, arguments: Dict[str, Any], tool_name: str
    ) -> SimulationResult:
        channel = str(arguments.get("channel", "#unknown"))
        message = str(arguments.get("message", ""))[:120]
        is_public = channel.startswith("#")
        members = int(arguments.get("member_count", 0))
        has_broadcast = any(tag in message for tag in ["@here", "@channel"])
        impact = [
            f"+ Would post in channel: {channel}",
            f"~ Channel visibility: {'public' if is_public else 'private'}",
            f"~ Members who would see this: {members}",
            f"~ Message preview: {message}",
        ]
        impact.append(f"~ Contains @here/@channel: {'yes' if has_broadcast else 'no'}")
        side_effects = ["Team-visible communication event."]
        risk = "low"
        if is_public:
            impact.append("! WARNING: Public channel exposure possible")
            side_effects.append("Message may be visible to broad audience.")
            risk = "medium"
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=impact,
            reversible=True,
            risk_assessment=risk,
            estimated_side_effects=side_effects,
        )

    def _simulate_jira_update(
        self, action_id: str, arguments: Dict[str, Any], tool_name: str
    ) -> SimulationResult:
        issue_key = str(arguments.get("issue_key", "UNKNOWN-0"))
        changes = arguments.get("changes", {})
        impact = [f"+ Would update issue: {issue_key}"]
        for field, value in changes.items():
            old_value = arguments.get("original", {}).get(field, "(unknown)")
            impact.append(f"~ {field}: {old_value} -> {value}")
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=impact,
            reversible=True,
            risk_assessment="medium" if changes else "low",
            estimated_side_effects=["Issue history entry will be created."],
        )

    def _simulate_database_query(
        self, action_id: str, arguments: Dict[str, Any], tool_name: str
    ) -> SimulationResult:
        query = str(arguments.get("query", "")).strip()
        query_lower = query.lower()
        write_keywords = ("update", "delete", "insert", "drop", "alter", "truncate")
        is_write = any(word in query_lower for word in write_keywords)
        tables = arguments.get("tables", [])
        estimated_rows = int(arguments.get("estimated_rows", 0))
        if not tables:
            tables = ["(undetermined)"]
        query_type = "SELECT"
        for keyword in ("INSERT", "UPDATE", "DELETE", "DROP"):
            if keyword.lower() in query_lower:
                query_type = keyword
                break
        impact = [
            f"+ Query type: {query_type}",
            f"~ Tables affected: {', '.join(str(t) for t in tables)}",
            f"~ Estimated rows affected: {estimated_rows}",
            f"~ Reversible: {'yes' if not is_write else 'no'}",
        ]
        if is_write:
            impact.append("! WARNING: Destructive or mutating SQL detected")
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=impact,
            reversible=not is_write,
            risk_assessment="high" if is_write else "low",
            estimated_side_effects=["Database load and lock behavior may vary by table size."],
        )

    def _simulate_generic_api(
        self, action_id: str, arguments: Dict[str, Any], tool_name: str
    ) -> SimulationResult:
        method = str(arguments.get("method", "GET")).upper()
        endpoint = str(arguments.get("endpoint", arguments.get("url", "/unknown")))
        destructive = method in {"DELETE", "PATCH", "PUT"} or "delete" in endpoint.lower()
        impact = [
            f"+ Method: {method}",
            f"~ Endpoint: {endpoint}",
            f"~ Destructive: {'yes' if destructive else 'no'}",
        ]
        if destructive:
            impact.append("! WARNING: Potentially destructive API operation")
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=impact,
            reversible=not destructive,
            risk_assessment="high" if destructive else "medium",
            estimated_side_effects=["External service state may change."],
        )
