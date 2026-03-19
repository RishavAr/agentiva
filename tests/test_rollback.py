import uuid

import pytest

from agentshield.modes.rollback import RollbackEngine


def _id() -> str:
    return str(uuid.uuid4())


def test_capture_state_creates_plan() -> None:
    engine = RollbackEngine()
    action_id = _id()
    plan = engine.capture_state(action_id, "jira_update", {"fields": {"status": "Done"}})
    assert plan.action_id == action_id
    assert plan.reversible is True


def test_rollback_executes_for_jira() -> None:
    engine = RollbackEngine()
    action_id = _id()
    engine.capture_state(action_id, "jira_update", {"fields": {"priority": "Low"}})
    result = engine.rollback(action_id)
    assert result.rollback_executed is True
    assert any("Restore original Jira fields" in s for s in result.undo_steps)


def test_rollback_executes_for_slack() -> None:
    engine = RollbackEngine()
    action_id = _id()
    engine.capture_state(action_id, "slack_post", {"ts": "12345.67"})
    result = engine.rollback(action_id)
    assert result.rollback_executed is True
    assert any("Delete Slack message" in s for s in result.undo_steps)


def test_rollback_executes_for_database() -> None:
    engine = RollbackEngine()
    action_id = _id()
    engine.capture_state(action_id, "database_query", {"snapshot_id": "snap-1"})
    result = engine.rollback(action_id)
    assert result.rollback_executed is True
    assert any("snapshot" in s.lower() for s in result.undo_steps)


def test_non_reversible_email_is_clearly_marked() -> None:
    engine = RollbackEngine()
    action_id = _id()
    plan = engine.capture_state(action_id, "gmail_send", {})
    assert plan.reversible is False
    result = engine.rollback(action_id)
    assert result.rollback_executed is False


def test_custom_handler_registration() -> None:
    engine = RollbackEngine()

    @engine.register("custom")
    def _handler(plan, _):
        plan.undo_steps = ["custom undo"]
        return plan

    action_id = _id()
    engine.capture_state(action_id, "custom", {})
    result = engine.rollback(action_id)
    assert result.undo_steps == ["custom undo"]


def test_missing_plan_raises_key_error() -> None:
    engine = RollbackEngine()
    with pytest.raises(KeyError):
        engine.rollback("missing")


def test_all_plans_returns_all_entries() -> None:
    engine = RollbackEngine()
    engine.capture_state(_id(), "jira_update", {})
    engine.capture_state(_id(), "slack_post", {})
    plans = engine.all_plans()
    assert len(plans) == 2


def test_get_plan_returns_none_for_unknown() -> None:
    engine = RollbackEngine()
    assert engine.get_plan("unknown") is None
