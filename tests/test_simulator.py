import uuid

from agentshield.modes.simulator import ActionSimulator, SimulationResult


def _id() -> str:
    return str(uuid.uuid4())


def test_gmail_simulator_external_recipient_warning() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "gmail_send", {"to": "hacker@evil.com", "subject": "Confidential"})
    assert any("External recipient" in line for line in result.impact)
    assert result.reversible is False


def test_gmail_simulator_internal_recipient() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "gmail_send", {"to": "dev@yourcompany.com", "subject": "Hello"})
    assert any("Would send email" in line for line in result.impact)
    assert result.risk_assessment in {"low", "medium", "high"}


def test_slack_simulator_public_channel_warning() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "slack_post", {"channel": "#engineering", "message": "status"})
    assert any("Public channel" in line for line in result.impact)


def test_jira_simulator_diff_output_contains_old_and_new() -> None:
    sim = ActionSimulator()
    result = sim.simulate(
        _id(),
        "jira_update",
        {
            "issue_key": "PROJ-1",
            "changes": {"priority": "high"},
            "original": {"priority": "medium"},
        },
    )
    assert any("priority: medium -> high" in line for line in result.impact)


def test_database_query_write_detection() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "database_query", {"query": "DELETE FROM users", "tables": ["users"]})
    assert any("mutating SQL" in line or "Destructive" in line for line in result.impact)
    assert result.reversible is False


def test_generic_api_destructive_detection() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "generic_api", {"method": "DELETE", "endpoint": "/v1/users/1"})
    assert result.risk_assessment == "high"


def test_unknown_tool_falls_back_to_generic_api() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "unknown_tool", {"method": "GET", "endpoint": "/status"})
    assert isinstance(result, SimulationResult)
    assert result.tool_name == "unknown_tool"


def test_custom_simulator_registration() -> None:
    sim = ActionSimulator()

    @sim.register("custom_tool")
    def _custom(action_id: str, arguments: dict, tool_name: str) -> SimulationResult:
        return SimulationResult(
            action_id=action_id,
            tool_name=tool_name,
            impact=[f"+ custom {arguments.get('x')}"],
            reversible=True,
            risk_assessment="low",
            estimated_side_effects=[],
        )

    result = sim.simulate(_id(), "custom_tool", {"x": "ok"})
    assert result.impact == ["+ custom ok"]


def test_diff_output_prefixes_are_human_readable() -> None:
    sim = ActionSimulator()
    result = sim.simulate(_id(), "gmail_send", {"to": "a@b.com", "subject": "x"})
    assert any(line.startswith(("+", "~", "!")) for line in result.impact)
