"""Comprehensive edge-case and stress tests for AgentShield."""

import asyncio
from typing import Dict, List

import pytest
import yaml
from fastapi.testclient import TestClient

from agentshield.api import server
from agentshield.interceptor.core import AgentShield


@pytest.fixture
def shield() -> AgentShield:
    """Provide a fresh AgentShield instance for unit-level tests."""
    return AgentShield(mode="shadow")


@pytest.fixture
def api_client() -> TestClient:
    """Provide a fresh API client with clean in-memory server state."""
    with TestClient(server.app) as client:
        if server._shield is not None:
            server._shield.audit_log.clear()
            server._shield.mode = "shadow"
        server._request_counts_by_agent.clear()
        yield client


class TestConcurrentInterceptions:
    """Stress tests for concurrent interception and log integrity."""

    def test_50_simultaneous_interceptions(self, shield: AgentShield) -> None:
        """Ensures 50 concurrent calls all complete, log correctly, and keep unique IDs."""

        async def _run() -> List:
            tasks = [
                shield.intercept(
                    tool_name=f"tool_{i}",
                    arguments={"index": i, "payload": f"value_{i}"},
                    agent_id=f"agent_{i % 5}",
                )
                for i in range(50)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(_run())
        assert len(results) == 50, "Expected 50 interception results from gather()."
        assert len(shield.audit_log) == 50, "Expected all 50 actions to be appended to audit log."

        ids = [action.id for action in results]
        assert len(set(ids)) == 50, "Each intercepted action must have a globally unique ID."
        assert all(action.tool_name.startswith("tool_") for action in results), (
            "Tool names should remain intact under concurrent interception."
        )


class TestMalformedInputs:
    """Validates resilience against malformed or unusual input shapes."""

    def test_unusual_tool_names_and_arguments(self, shield: AgentShield) -> None:
        """Ensures unusual strings and nested payloads do not crash interception."""

        deep_nested: Dict[str, Dict] = {"level1": {}}
        current = deep_nested["level1"]
        for level in range(2, 11):
            current[f"level{level}"] = {}
            current = current[f"level{level}"]
        current["value"] = "deep"

        cases = [
            {
                "tool_name": "'; DROP TABLE users; --",
                "arguments": {"query": "unsafe"},
            },
            {
                "tool_name": "工具_发送_メール",
                "arguments": {"emoji": "🚀"},
            },
            {
                "tool_name": "t" * 10000,
                "arguments": {},
            },
            {
                "tool_name": "null_values",
                "arguments": {"a": None, "b": {"inner": None}},
            },
            {
                "tool_name": "nested_10_levels",
                "arguments": deep_nested,
            },
            {
                "tool_name": "special_chars_!@#$%^&*()[]{}<>?/\\|",
                "arguments": {
                    "field_!@#": "value_<>?/\\|",
                    "quote": "\"double\" and 'single'",
                },
            },
        ]

        for case in cases:
            action = asyncio.run(
                shield.intercept(case["tool_name"], case["arguments"], agent_id="edge-agent")
            )
            assert action.id, "Each malformed-input case should still produce an action ID."
            assert action.arguments == case["arguments"], (
                "Arguments should be preserved without silent mutation."
            )


class TestPolicyEdgeCases:
    """Covers policy behavior under unusual and minimal configurations."""

    def test_overlapping_rules_first_match_wins(self, tmp_path) -> None:
        """Ensures earlier matching rule has priority over later overlapping rules."""

        policy_path = tmp_path / "overlap.yaml"
        policy_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "default_mode": "shadow",
                    "rules": [
                        {
                            "name": "first_rule",
                            "tool": "send_email",
                            "action": "shadow",
                            "risk_score": 0.2,
                        },
                        {
                            "name": "second_rule",
                            "tool": "send_email",
                            "action": "block",
                            "risk_score": 0.9,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        local_shield = AgentShield(mode="live", policy_path=str(policy_path))
        action = asyncio.run(local_shield.intercept("send_email", {"to": "x@example.com"}))
        assert action.decision == "shadow", "Policy engine should apply first matching rule."
        assert action.risk_score == 0.2, "Risk should come from first matching rule."

    def test_wildcard_patterns_and_missing_fields(self, tmp_path) -> None:
        """Ensures wildcard rule matching works and missing fields do not crash checks."""

        policy_path = tmp_path / "wildcards.yaml"
        policy_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "default_mode": "shadow",
                    "rules": [
                        {
                            "name": "missing_field_condition",
                            "tool": "send_*",
                            "condition": {
                                "field": "arguments.non_existent",
                                "operator": "equals",
                                "value": "x",
                            },
                            "action": "block",
                            "risk_score": 1.0,
                        },
                        {
                            "name": "wildcard_fallback",
                            "tool": "send_*",
                            "action": "approve",
                            "risk_score": 0.6,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        local_shield = AgentShield(mode="shadow", policy_path=str(policy_path))
        action = asyncio.run(local_shield.intercept("send_sms", {"phone": "123"}))
        assert action.decision == "approve", (
            "When a conditioned rule misses, engine should continue and match later wildcard rule."
        )
        assert action.risk_score == 0.6, "Wildcard fallback rule should set risk score."

    def test_zero_rules_and_default_only_policy(self, tmp_path) -> None:
        """Ensures policies with no rules still return stable default behavior."""

        zero_rules_path = tmp_path / "zero_rules.yaml"
        zero_rules_path.write_text(
            yaml.safe_dump({"version": 1, "default_mode": "shadow", "rules": []}),
            encoding="utf-8",
        )
        shield_zero = AgentShield(mode="live", policy_path=str(zero_rules_path))
        action_zero = asyncio.run(shield_zero.intercept("anything", {}))
        assert action_zero.decision == "shadow", "No-rules policy should use default_mode."

        default_only_path = tmp_path / "default_only.yaml"
        default_only_path.write_text(
            yaml.safe_dump({"version": 1, "default_mode": "block"}),
            encoding="utf-8",
        )
        shield_default_only = AgentShield(mode="shadow", policy_path=str(default_only_path))
        action_default = asyncio.run(shield_default_only.intercept("anything", {}))
        assert action_default.decision == "block", (
            "Policy with only default_mode should still evaluate safely."
        )


class TestModeSwitching:
    """Verifies operational consistency when modes change during runtime."""

    def test_mode_switch_mid_operation(self, shield: AgentShield) -> None:
        """Ensures actions reflect mode at interception time before and after switch."""

        before = [asyncio.run(shield.intercept("send_email", {"to": f"user{i}@x.com"})) for i in range(5)]
        shield.mode = "live"
        after = [asyncio.run(shield.intercept("send_email", {"to": f"user{i}@x.com"})) for i in range(5)]

        assert all(a.mode == "shadow" for a in before), (
            "Actions intercepted before switch must remain tagged with old mode."
        )
        assert all(a.mode == "live" for a in after), (
            "Actions intercepted after switch must use new mode."
        )
        assert all(a.decision == "allow" for a in after), (
            "Live mode should map to 'allow' decision when no policy overrides."
        )


class TestAuditLogStress:
    """High-volume tests for logging, filtering, and report math."""

    def test_audit_log_1000_actions_pagination_filters_and_report(self, api_client: TestClient) -> None:
        """Ensures large audit datasets preserve pagination, filtering, and aggregate metrics."""

        for i in range(1000):
            tool = "send_email" if i % 2 == 0 else "create_ticket"
            payload = {
                "tool_name": tool,
                "arguments": {"index": i},
                "agent_id": f"agent-{i % 10}",
            }
            response = api_client.post("/api/v1/intercept", json=payload)
            assert response.status_code == 200, "Bulk interception should not fail under load."

        page = api_client.get("/api/v1/audit", params={"limit": 50, "offset": 100})
        assert page.status_code == 200, "Audit pagination endpoint should return successfully."
        assert len(page.json()) == 50, "Expected exactly 50 paginated records."

        filtered = api_client.get("/api/v1/audit", params={"tool_name": "send_email", "limit": 1000})
        assert filtered.status_code == 200, "Audit filter by tool should succeed at scale."
        assert len(filtered.json()) == 500, "Half of 1000 generated actions should be send_email."

        report = api_client.get("/api/v1/report")
        assert report.status_code == 200, "Report endpoint should succeed on large datasets."
        body = report.json()
        assert body["total_actions"] == 1000, "Report total_actions should match generated load."
        assert body["by_tool"]["send_email"] == 500, "Tool aggregation must be accurate."
        assert body["by_tool"]["create_ticket"] == 500, "Tool aggregation must be accurate."
        assert 0.0 <= body["avg_risk_score"] <= 1.0, "Average risk should remain bounded."


class TestApiInputValidation:
    """Tests API schema validation and robustness for malformed payloads."""

    def test_missing_fields_wrong_types_and_large_payload(self, api_client: TestClient) -> None:
        """Ensures validation catches malformed requests and handles large payload safely."""

        missing = api_client.post("/api/v1/intercept", json={"arguments": {"x": 1}})
        assert missing.status_code == 422, "Missing required tool_name should be rejected."

        wrong_type = api_client.post(
            "/api/v1/intercept",
            json={"tool_name": 123, "arguments": {}, "agent_id": "a"},
        )
        assert wrong_type.status_code == 422, "Numeric tool_name should fail string validation."

        extra = api_client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "send_email",
                "arguments": {"to": "a@b.com"},
                "agent_id": "a",
                "unexpected": "ignored",
            },
        )
        assert extra.status_code == 200, (
            "Unexpected extra fields should not crash endpoint under default model config."
        )

        large_payload = api_client.post(
            "/api/v1/intercept",
            json={
                "tool_name": "big_payload",
                "arguments": {"blob": "x" * 200000},
                "agent_id": "stress-agent",
            },
        )
        assert large_payload.status_code == 200, "Large JSON payload should be handled successfully."


class TestRiskScoreBoundaries:
    """Verifies risk score boundary handling and filtering semantics."""

    def test_risk_score_0_and_1_and_min_risk_boundaries(self, tmp_path, api_client: TestClient) -> None:
        """Ensures exact 0.0/1.0 scores are preserved and min_risk filtering behaves at boundaries."""

        policy_path = tmp_path / "boundaries.yaml"
        policy_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "default_mode": "shadow",
                    "rules": [
                        {"name": "zero_risk", "tool": "zero_tool", "action": "shadow", "risk_score": 0.0},
                        {"name": "max_risk", "tool": "max_tool", "action": "block", "risk_score": 1.0},
                    ],
                }
            ),
            encoding="utf-8",
        )

        server._shield = AgentShield(mode="shadow", policy_path=str(policy_path))
        server._shield.audit_log.clear()

        r1 = api_client.post("/api/v1/intercept", json={"tool_name": "zero_tool", "arguments": {}})
        r2 = api_client.post("/api/v1/intercept", json={"tool_name": "max_tool", "arguments": {}})
        assert r1.status_code == 200 and r2.status_code == 200, "Boundary risk actions should intercept cleanly."

        b1 = r1.json()
        b2 = r2.json()
        assert b1["risk_score"] == 0.0, "Risk score should preserve exact lower boundary 0.0."
        assert b2["risk_score"] == 1.0, "Risk score should preserve exact upper boundary 1.0."

        min_zero = api_client.get("/api/v1/audit", params={"min_risk": 0.0, "limit": 10})
        min_one = api_client.get("/api/v1/audit", params={"min_risk": 1.0, "limit": 10})
        assert len(min_zero.json()) == 2, "min_risk=0.0 should include all boundary records."
        assert len(min_one.json()) == 1, "min_risk=1.0 should include only max-risk records."
        assert min_one.json()[0]["tool_name"] == "max_tool", "Highest boundary filter should return max-risk tool."


class TestRapidModeSwitching:
    """Stress tests frequent mode mutation for consistency and stability."""

    def test_switch_mode_100_times_rapidly(self, api_client: TestClient) -> None:
        """Ensures repeated mode changes remain consistent without invalid state."""

        modes = ["shadow", "live", "approval"]
        for i in range(100):
            target_mode = modes[i % len(modes)]
            response = api_client.post(f"/api/v1/mode/{target_mode}")
            assert response.status_code == 200, "Rapid mode switch request should not fail."
            assert response.json()["mode"] == target_mode, "Mode response should reflect requested target."

        health = api_client.get("/health")
        assert health.status_code == 200, "Health endpoint should remain available after rapid mode changes."
        final_mode = health.json()["mode"]
        assert final_mode in modes, "Final mode must stay within allowed set."
