from datetime import datetime

from agentshield.policy.smart_scorer import SmartRiskScorer


def test_tool_sensitivity_email_higher_than_jira() -> None:
    scorer = SmartRiskScorer()
    email = scorer.score_action("gmail_send", {"to": "a@b.com"})
    jira = scorer.score_action("jira_update", {"issue_key": "A-1"})
    assert email.score >= jira.score


def test_external_recipient_increases_risk() -> None:
    scorer = SmartRiskScorer()
    external = scorer.score_action("gmail_send", {"to": "hacker@evil.com"})
    internal = scorer.score_action("gmail_send", {"to": "dev@yourcompany.com"})
    assert external.score > internal.score


def test_bulk_pattern_detection() -> None:
    scorer = SmartRiskScorer()
    single = scorer.score_action("generic_api", {}, bulk_size=1)
    bulk = scorer.score_action("generic_api", {}, bulk_size=100)
    assert bulk.score > single.score


def test_time_based_signal_midnight_vs_afternoon() -> None:
    scorer = SmartRiskScorer()
    night = scorer.score_action("generic_api", {}, timestamp=datetime(2026, 1, 1, 3, 0, 0))
    day = scorer.score_action("generic_api", {}, timestamp=datetime(2026, 1, 1, 14, 0, 0))
    assert night.score > day.score


def test_agent_reputation_new_higher_risk_than_trusted() -> None:
    scorer = SmartRiskScorer()
    new = scorer.score_action("generic_api", {}, agent_reputation="new")
    trusted = scorer.score_action("generic_api", {}, agent_reputation="trusted")
    assert new.score < trusted.score


def test_content_keyword_detection() -> None:
    scorer = SmartRiskScorer()
    risky = scorer.score_action("database_query", {"query": "DROP TABLE users"})
    neutral = scorer.score_action("database_query", {"query": "SELECT * FROM users"})
    assert risky.score > neutral.score


def test_frequency_signal_for_high_rate() -> None:
    scorer = SmartRiskScorer()
    low = scorer.score_action("generic_api", {}, agent_id="a", recent_actions_per_minute=10)
    high = scorer.score_action("generic_api", {}, agent_id="a", recent_actions_per_minute=120)
    assert high.score > low.score


def test_combined_scoring_outputs_recommendation() -> None:
    scorer = SmartRiskScorer()
    result = scorer.score_action(
        "gmail_send",
        {"to": "hacker@evil.com", "subject": "confidential drop"},
        recent_actions_per_minute=150,
        bulk_size=60,
        agent_reputation="new",
    )
    assert 0.0 <= result.score <= 1.0
    assert result.recommendation in {"allow", "shadow", "approve", "block"}


def test_llm_judge_opt_in_adds_signal() -> None:
    scorer = SmartRiskScorer(enable_llm_judge=True, llm_client=object())
    result = scorer.score_action("generic_api", {})
    assert any("LLM judge enabled" in signal for signal in result.signals)


def test_custom_weights_change_score() -> None:
    baseline = SmartRiskScorer()
    weighted = SmartRiskScorer(weights={"tool_sensitivity": 0.9, "content_analysis": 0.0})
    a = baseline.score_action("gmail_send", {"to": "dev@yourcompany.com"})
    b = weighted.score_action("gmail_send", {"to": "dev@yourcompany.com"})
    assert a.score != b.score
