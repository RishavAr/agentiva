from __future__ import annotations

import asyncio
import textwrap
from datetime import UTC, datetime
from pathlib import Path

from agentshield import AgentShield
from agentshield.api.chat import ShieldChat


def _write_policy(tmp_path: Path, yaml_text: str) -> str:
    p = tmp_path / "policy.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return str(p)


def _run(coro):
    return asyncio.run(coro)


def test_hierarchical_approval_auto_approve_small_amount(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            approval_chains:
              financial:
                - threshold: 1000
                  action: allow
                - threshold: 10000
                  action: approve
                  approver: manager
                - threshold: 1000000
                  action: approve
                  approver: cfo
                  require_dual: true
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(
        shield.intercept(
            "transfer_funds",
            {"amount": 500},
            agent_id="agent-1",
            timestamp="2026-01-01T12:00:00+00:00",
        )
    )
    assert action.decision == "allow"


def test_hierarchical_approval_requires_manager_for_medium(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            approval_chains:
              financial:
                - threshold: 1000
                  action: allow
                - threshold: 10000
                  action: approve
                  approver: manager
                - threshold: 1000000
                  action: approve
                  approver: cfo
                  require_dual: true
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(shield.intercept("transfer_funds", {"amount": 5000}, agent_id="agent-1"))
    assert action.decision == "approve"
    assert action.result.get("approver") == "manager"
    assert action.result.get("require_dual") is False


def test_hierarchical_approval_requires_dual_sign_for_large(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            approval_chains:
              financial:
                - threshold: 1000
                  action: allow
                - threshold: 10000
                  action: approve
                  approver: manager
                - threshold: 1000000
                  action: approve
                  approver: cfo
                  require_dual: true
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(shield.intercept("transfer_funds", {"amount": 2000000}, agent_id="agent-1"))
    assert action.decision == "approve"
    assert action.result.get("approver") == "cfo"
    assert action.result.get("require_dual") is True


def test_mandatory_action_never_blocked(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            mandatory_actions:
              - name: adverse_event_report
                tool: send_email
                condition:
                  field: arguments.subject
                  operator: contains
                  value: "ADVERSE EVENT"
                action: always_allow
                reason: "FDA requires adverse event reporting within 24 hours"
            rules:
              - name: block_external_email
                tool: send_email
                condition:
                  field: arguments.to
                  operator: not_contains
                  value: "@yourcompany.com"
                action: block
                risk_score: 0.9
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(
        shield.intercept(
            "send_email",
            {"to": "customer@evil.com", "subject": "ADVERSE EVENT: reaction report"},
            agent_id="agent-1",
        )
    )
    assert action.decision == "allow"
    assert action.result.get("mandatory") is True
    assert "FDA requires adverse event reporting" in action.result.get("reason", "")


def test_mandatory_action_still_logged(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            mandatory_actions:
              - name: security_incident_alert
                tool: send_slack_message
                condition:
                  field: arguments.channel
                  operator: equals
                  value: "#security-incidents"
                action: always_allow
                reason: "Security alerts must never be suppressed"
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(
        shield.intercept(
            "send_slack_message",
            {"channel": "#security-incidents", "message": "incident!"},
            agent_id="agent-1",
        )
    )
    assert action.decision == "allow"
    assert len(shield.audit_log) == 1
    assert shield.audit_log[0].result.get("mandatory") is True


def test_geo_eu_gdpr_blocks_non_eu_transfer(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            geo_policies:
              EU:
                - name: gdpr_consent_required
                  tool: read_customer_data
                  condition:
                    field: context.customer_region
                    operator: equals
                    value: "EU"
                  action: approve
                  reason: "GDPR: explicit consent required for EU customer data access"
                - name: eu_data_residency
                  tool: send_email
                  condition:
                    field: context.customer_region
                    operator: equals
                    value: "EU"
                  additional_condition:
                    field: arguments.to
                    operator: not_contains
                    value: ".eu"
                  action: block
                  reason: "EU data cannot be transferred outside EU without adequacy decision"
            """
        ),
    )

    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(
        shield.intercept(
            "send_email",
            {"to": "user@outside.com", "subject": "data export"},
            agent_id="agent-1",
            context={"customer_region": "EU"},
        )
    )
    assert action.decision == "block"
    assert "EU data cannot be transferred outside EU" in action.result.get("reason", "")


def test_geo_california_ccpa_shadows_data_access(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            geo_policies:
              US_CALIFORNIA:
                - name: ccpa_right_to_know
                  tool: read_customer_data
                  condition:
                    field: context.customer_state
                    operator: equals
                    value: "CA"
                  action: shadow
                  reason: "CCPA: log all data access for California residents"
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    action = _run(
        shield.intercept(
            "read_customer_data",
            {"customer_id": "C-1001", "fields": ["name", "email"]},
            agent_id="agent-1",
            context={"customer_state": "CA"},
        )
    )
    assert action.decision == "shadow"


def test_copilot_explains_geo_block_reason(tmp_path) -> None:
    policy = _write_policy(
        tmp_path,
        textwrap.dedent(
            """
            version: 1
            default_mode: shadow
            geo_policies:
              EU:
                - name: eu_data_residency
                  tool: send_email
                  condition:
                    field: context.customer_region
                    operator: equals
                    value: "EU"
                  additional_condition:
                    field: arguments.to
                    operator: not_contains
                    value: ".eu"
                  action: block
                  reason: "EU data cannot be transferred outside EU without adequacy decision"
            """
        ),
    )
    shield = AgentShield(mode="shadow", policy_path=policy)
    _run(
        shield.intercept(
            "send_email",
            {"to": "user@outside.com", "subject": "data export"},
            agent_id="agent-1",
            context={"customer_region": "EU"},
        )
    )

    chat = ShieldChat(shield)
    resp = _run(chat.ask("why was this blocked?"))
    assert "EU data cannot be transferred outside EU without adequacy decision" in resp.answer

