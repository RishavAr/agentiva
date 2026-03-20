from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import textwrap
from pathlib import Path
from typing import Any, Dict, List

from agentshield import AgentShield
from agentshield.api.chat import ShieldChat
from agentshield.interceptor.core import InterceptedAction


def _write_policy(tmp_path: Path, yaml_text: str) -> str:
    p = tmp_path / "policy.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return str(p)


def _action(
    *,
    tool_name: str,
    agent_id: str,
    decision: str,
    risk_score: float,
    policy_rule: str,
    arguments: Dict[str, Any] | None = None,
) -> InterceptedAction:
    return InterceptedAction(
        id="x",
        timestamp=datetime.now(UTC).isoformat(),
        tool_name=tool_name,
        arguments=arguments or {},
        agent_id=agent_id,
        risk_score=risk_score,
        decision=decision,
        mode="shadow",
        result={"policy_rule": policy_rule},
    )


def test_role_based_policy_sales_agent_can_email_externally(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            roles:
              support_agent:
                allowed_external_emails: ["*@customer-domain.com"]
                can_read_customer_data: true
                can_read_ssn: false
                max_refund_amount: 500
              sales_agent:
                allowed_external_emails: ["*"]
                can_read_customer_data: true
                can_read_financial: false
            rules:
              - name: block_external_email
                tool: send_email
                condition:
                  field: arguments.to
                  operator: not_contains
                  value: "@yourcompany.com"
                action: block
                risk_score: 0.9
              - name: allow_internal_email
                tool: send_email
                action: allow
                risk_score: 0.2
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    action = asyncio.run(
        shield.intercept(
            "send_email",
            {"to": "hacker@evil.com", "subject": "Secrets"},
            agent_id="sales_agent",
        )
    )
    assert action.decision == "allow"


def test_role_based_policy_support_agent_cannot_read_ssn(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            roles:
              support_agent:
                can_read_customer_data: true
                can_read_ssn: false
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    action = asyncio.run(
        shield.intercept(
            "read_customer_data",
            {"customer_id": "C-1", "fields": ["name", "ssn"]},
            agent_id="support_agent",
        )
    )
    assert action.decision == "block"


def test_context_aware_self_access_lower_risk(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    args = {"customer_id": "C-1001", "fields": ["name", "email", "medical_history"]}

    safe = asyncio.run(
        shield.intercept(
            "read_customer_data",
            args,
            agent_id="agent-x",
            context={"requested_by": "customer", "customer_id_match": True},
            timestamp=now,
        )
    )
    unsafe = asyncio.run(
        shield.intercept(
            "read_customer_data",
            args,
            agent_id="agent-x",
            context={"requested_by": "agent", "customer_id_match": False},
            timestamp=now,
        )
    )
    assert safe.risk_score < unsafe.risk_score


def test_context_aware_doctor_can_read_medical(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    args = {"customer_id": "C-1001", "fields": ["medical_history"]}

    doctor = asyncio.run(
        shield.intercept(
            "read_customer_data",
            args,
            agent_id="agent-x",
            context={"user_role": "doctor", "customer_id_match": True, "session_type": "support_ticket"},
            timestamp=now,
        )
    )
    patient = asyncio.run(
        shield.intercept(
            "read_customer_data",
            args,
            agent_id="agent-y",
            context={"user_role": "patient", "customer_id_match": True, "session_type": "support_ticket"},
            timestamp=now,
        )
    )
    assert doctor.risk_score < patient.risk_score


def test_behavioral_drift_gradual_escalation_detected(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            rules:
              - name: allow_generic_api
                tool: generic_api
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    agent_id = "drift-agent"
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Previous hour: low-risk SELECTs
    for i in range(3):
        asyncio.run(
            shield.intercept(
                "generic_api",
                {"query": "SELECT * FROM users"},
                agent_id=agent_id,
                timestamp=now - timedelta(hours=1.5) + timedelta(minutes=i * 2),
            )
        )

    # Last hour: high-risk DROP TABLEs
    high_risks: List[float] = []
    for i in range(3):
        r = asyncio.run(
            shield.intercept(
                "generic_api",
                {"query": "DROP TABLE users"},
                agent_id=agent_id,
                timestamp=now - timedelta(minutes=15) + timedelta(minutes=i * 2),
            )
        )
        high_risks.append(r.risk_score)

    assert high_risks[1] > high_risks[0]


def test_baseline_within_normal_lower_risk(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            baselines:
              support_agent:
                expected_actions_per_hour: 10
                expected_tools: [read_customer_data]
                expected_data_access_per_hour: 20
                normal_hours: "00:00-23:59"
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    args = {"fields": ["name", "email", "medical_history"]}  # data_volume=3

    r_within = asyncio.run(
        shield.intercept(
            "read_customer_data",
            args,
            agent_id="support_agent",
            timestamp=now,
        )
    )

    # Compare against an "outside baseline" config.
    policy_outside = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            baselines:
              support_agent:
                expected_actions_per_hour: 1
                expected_tools: [read_customer_data]
                expected_data_access_per_hour: 1
                normal_hours: "00:00-23:59"
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )
    shield_out = AgentShield(mode="shadow", policy_path=policy_outside)
    # Prepopulate to exceed baseline.
    for _ in range(4):
        asyncio.run(
            shield_out.intercept(
                "read_customer_data",
                args,
                agent_id="support_agent",
                timestamp=now - timedelta(minutes=1),
            )
        )
    r_outside = asyncio.run(
        shield_out.intercept(
            "read_customer_data",
            args,
            agent_id="support_agent",
            timestamp=now,
        )
    )
    assert r_within.risk_score < r_outside.risk_score


def test_baseline_outside_normal_higher_risk(tmp_path) -> None:
    # This test is the mirror of the prior one: risk should go up when outside baseline.
    policy_within = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            baselines:
              support_agent:
                expected_actions_per_hour: 10
                expected_tools: [read_customer_data]
                expected_data_access_per_hour: 20
                normal_hours: "00:00-23:59"
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )
    policy_outside = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            baselines:
              support_agent:
                expected_actions_per_hour: 1
                expected_tools: [read_customer_data]
                expected_data_access_per_hour: 1
                normal_hours: "00:00-23:59"
            rules:
              - name: allow_read_customer_data
                tool: read_customer_data
                action: allow
                risk_score: 0.2
            """
        ),
    )

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    args = {"fields": ["name", "email", "medical_history"]}

    within = AgentShield(mode="shadow", policy_path=policy_within)
    r_within = asyncio.run(
        within.intercept("read_customer_data", args, agent_id="support_agent", timestamp=now)
    )

    outside = AgentShield(mode="shadow", policy_path=policy_outside)
    for _ in range(4):
        asyncio.run(
            outside.intercept(
                "read_customer_data",
                args,
                agent_id="support_agent",
                timestamp=now - timedelta(minutes=1),
            )
        )
    r_outside = asyncio.run(
        outside.intercept("read_customer_data", args, agent_id="support_agent", timestamp=now)
    )
    assert r_outside.risk_score > r_within.risk_score


def test_whitelist_trusted_domain_lower_risk(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            whitelists:
              trusted_domains:
                - "*.yourcompany.com"
            rules:
              - name: allow_external_api
                tool: call_external_api
                action: allow
                risk_score: 0.2
            """
        ),
    )

    now_agent = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    shield = AgentShield(mode="shadow", policy_path=policy)

    trusted = asyncio.run(
        shield.intercept(
            "call_external_api",
            {"url": "https://api.yourcompany.com/v1/account"},
            agent_id="w1",
            timestamp=now_agent,
        )
    )
    unknown = asyncio.run(
        shield.intercept(
            "call_external_api",
            {"url": "https://evil.example.com/v1/account"},
            agent_id="w2",
            timestamp=now_agent,
        )
    )
    assert trusted.risk_score < unknown.risk_score


def test_whitelist_unknown_domain_higher_risk(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            whitelists:
              trusted_domains:
                - "*.yourcompany.com"
            rules:
              - name: allow_external_api
                tool: call_external_api
                action: allow
                risk_score: 0.2
            """
        ),
    )
    now_agent = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    shield = AgentShield(mode="shadow", policy_path=policy)

    trusted = asyncio.run(
        shield.intercept(
            "call_external_api",
            {"url": "https://sub.yourcompany.com/health"},
            agent_id="w1",
            timestamp=now_agent,
        )
    )
    unknown = asyncio.run(
        shield.intercept(
            "call_external_api",
            {"url": "https://malware.example.org/ping"},
            agent_id="w2",
            timestamp=now_agent,
        )
    )
    assert unknown.risk_score > trusted.risk_score


def test_copilot_suggests_role_when_blocks_high(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            roles:
              sales_agent:
                allowed_external_emails: ["*"]
                can_read_customer_data: true
            rules:
              - name: block_external_email
                tool: send_email
                action: block
                risk_score: 0.9
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    shield.audit_log = []

    # Make it "high block rate": 10 blocked out of 20 actions.
    for _ in range(10):
        shield.audit_log.append(
            _action(
                tool_name="send_email",
                agent_id="unconfigured-agent",
                decision="block",
                risk_score=0.2,
                policy_rule="block_external_email",
                arguments={"to": "a@evil.com", "subject": "Re: hi"},
            )
        )
    for _ in range(10):
        shield.audit_log.append(
            _action(
                tool_name="create_jira_ticket",
                agent_id="unconfigured-agent",
                decision="shadow",
                risk_score=0.2,
                policy_rule="shadow_tickets",
                arguments={"title": "x"},
            )
        )

    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("my agent keeps getting blocked"))
    assert "Your agent doesn't have a role configured" in resp.answer
    assert "sales_agent" in resp.answer

