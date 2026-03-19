from fastapi.testclient import TestClient

from agentshield.api import server


def _new_client() -> TestClient:
    return TestClient(server.app)


def _reset_runtime_state() -> None:
    if server._shield is not None:
        server._shield.audit_log.clear()
        server._shield.mode = "shadow"


def test_health_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["version"] == "0.1.0"
        assert "uptime_seconds" in body
        assert body["mode"] in {"shadow", "live", "approval"}


def test_intercept_valid_input() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        payload = {
            "tool_name": "send_email",
            "arguments": {"to": "dev@yourcompany.com", "subject": "Hi"},
            "agent_id": "agent-a",
        }
        response = client.post("/api/v1/intercept", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["tool_name"] == "send_email"
        assert body["agent_id"] == "agent-a"
        assert body["decision"] in {"shadow", "block", "approve", "allow", "pending"}
        assert isinstance(body["risk_score"], float)


def test_intercept_invalid_input_empty_tool_name() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        payload = {"tool_name": "   ", "arguments": {}, "agent_id": "agent-a"}
        response = client.post("/api/v1/intercept", json=payload)
        assert response.status_code == 422


def test_audit_log_filters() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "outside@example.com"},
                "agent_id": "alpha",
            },
        )
        client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "create_ticket",
                "arguments": {"title": "Issue"},
                "agent_id": "beta",
            },
        )

        response = client.get("/api/v1/audit", params={"tool_name": "create_ticket"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["tool_name"] == "create_ticket"

        response = client.get("/api/v1/audit", params={"agent_id": "alpha"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["agent_id"] == "alpha"


def test_shadow_report_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        client.post(
            "/api/v1/intercept",
            json={"tool_name": "send_email", "arguments": {"to": "a@yourcompany.com"}},
        )
        client.post(
            "/api/v1/intercept",
            json={"tool_name": "create_ticket", "arguments": {"title": "Bug"}},
        )
        response = client.get("/api/v1/report")
        assert response.status_code == 200
        body = response.json()
        assert body["total_actions"] == 2
        assert "by_tool" in body
        assert "by_decision" in body
        assert "avg_risk_score" in body


def test_mode_change_endpoint() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.post("/api/v1/mode/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "mode": "live"}


def test_invalid_mode_error() -> None:
    with _new_client() as client:
        _reset_runtime_state()
        response = client.post("/api/v1/mode/not-real")
        assert response.status_code == 400
        assert "Mode must be" in response.json()["detail"]
