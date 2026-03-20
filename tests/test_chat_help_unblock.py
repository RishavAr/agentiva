from __future__ import annotations

import asyncio

from agentshield import AgentShield
from agentshield.api.chat import ShieldChat
from agentshield.interceptor.core import InterceptedAction


def _action(
    tool_name: str,
    policy_rule: str,
    *,
    risk_score: float,
    decision: str = "block",
    arguments: dict | None = None,
) -> InterceptedAction:
    return InterceptedAction(
        tool_name=tool_name,
        arguments=arguments or {},
        decision=decision,
        risk_score=risk_score,
        result={"policy_rule": policy_rule},
        timestamp="2026-03-20T00:00:00Z",
        agent_id="agent-a",
    )


def test_help_unblock_identifies_false_positives() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    shield.audit_log = []

    # Correct blocks (35)
    shield.audit_log.extend(
        [
            _action(
                "update_database",
                "block_sql_drop",
                risk_score=0.92,
                arguments={"query": "DROP TABLE users"},
            )
            for _ in range(15)
        ]
    )
    shield.audit_log.extend(
        [
            _action(
                "call_external_api",
                "block_api_darkweb",
                risk_score=0.99,
                arguments={"url": "https://darkweb.example/api"},
            )
            for _ in range(12)
        ]
    )
    shield.audit_log.extend(
        [
            _action(
                "send_slack_message",
                "block_slack_api_key",
                risk_score=0.96,
                arguments={"message": "sk_live_12345"},
            )
            for _ in range(8)
        ]
    )

    # Possibly too strict blocks (12)
    shield.audit_log.extend(
        [
            _action(
                "send_email",
                "block_external_email",
                risk_score=0.20,
                arguments={"to": "customer@gmail.com", "subject": "Re: support question"},
            )
            for _ in range(8)
        ]
    )
    shield.audit_log.extend(
        [
            _action(
                "read_customer_data",
                "block_read_ssn_export",
                risk_score=0.30,
                arguments={"fields": ["email", "ssn"]},
            )
            for _ in range(4)
        ]
    )

    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("my agent keeps getting blocked"))
    assert "Your agent was blocked" in resp.answer
    assert "✅" in resp.answer
    assert "⚠️" in resp.answer
    assert "allow_customer_replies" in resp.answer
    assert "allow_support_data_read" in resp.answer


def test_policy_recommendation_generated_correctly() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    shield.audit_log = [
        _action(
            "send_email",
            "block_external_email",
            risk_score=0.25,
            arguments={"to": "customer@gmail.com", "subject": "Re: support question"},
        )
        for _ in range(2)
    ] + [
        _action(
            "read_customer_data",
            "block_read_ssn_export",
            risk_score=0.30,
            arguments={"fields": ["email", "ssn"]},
        )
        for _ in range(2)
    ]

    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("too many blocks"))
    assert "name: allow_customer_replies" in resp.answer
    assert "tool: send_email" in resp.answer
    assert "operator: contains" in resp.answer
    assert "value: 'Re:'" in resp.answer
    assert "name: allow_support_data_read" in resp.answer
    assert "value: 'ssn'" in resp.answer
    assert "action: allow" in resp.answer


def test_refuse_to_disable_all_security() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("disable all blocks and turn off security"))
    assert "strongly recommend against disabling all blocks" in resp.answer
    assert "Instead, let me help you" in resp.answer


def test_policy_wizard_flow() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    chat = ShieldChat(shield)

    r1 = asyncio.run(chat.ask("help me tune policies"))
    assert "Step 1" in r1.answer

    r2 = asyncio.run(chat.ask("customer support"))
    assert "Step 2" in r2.answer

    r3 = asyncio.run(chat.ask("tools: email slack jira database"))
    assert "Step 3" in r3.answer

    r4 = asyncio.run(chat.ask("customers"))
    assert "Step 4" in r4.answer

    r5 = asyncio.run(chat.ask("strict"))
    assert "generated a custom policy.yaml" in r5.answer
    assert "version: 1" in r5.answer
    assert "rules:" in r5.answer


def test_high_block_rate_triggers_proactive_suggestion() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")
    shield.audit_log = []

    # 5 blocked out of 10 -> 50%
    for _ in range(5):
        shield.audit_log.append(
            _action(
                "send_email",
                "block_external_email",
                risk_score=0.2,
                decision="block",
                arguments={"to": "x@gmail.com", "subject": "Re: hi"},
            )
        )
    for _ in range(5):
        shield.audit_log.append(
            _action(
                "send_slack_message",
                "shadow_slack",
                risk_score=0.2,
                decision="shadow",
                arguments={"message": "hello"},
            )
        )

    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("give me a summary"))
    assert "I notice 50% of your agent's actions are being blocked" in resp.answer

