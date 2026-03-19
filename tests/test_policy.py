import asyncio

from agentshield import AgentShield


async def test_policy() -> None:
    shield = AgentShield(mode="shadow", policy_path="policies/default.yaml")

    a1 = await shield.intercept(
        "send_email", {"to": "hacker@evil.com", "subject": "Secrets"}
    )
    print(f"External email: {a1.decision} (risk: {a1.risk_score})")

    a2 = await shield.intercept(
        "send_email", {"to": "bob@yourcompany.com", "subject": "Hi"}
    )
    print(f"Company email: {a2.decision} (risk: {a2.risk_score})")

    a3 = await shield.intercept("create_ticket", {"title": "Bug fix"})
    print(f"Ticket: {a3.decision} (risk: {a3.risk_score})")

    assert a1.decision == "block"
    assert a2.decision == "shadow"
    assert a3.decision == "shadow"
    print("test_policy passed!")


if __name__ == "__main__":
    asyncio.run(test_policy())
