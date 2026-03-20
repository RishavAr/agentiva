"""Tests for ShieldChat and SmartChat."""

from __future__ import annotations

import asyncio

from agentshield import AgentShield
from agentshield.api.chat import ShieldChat, SmartChat


def test_basic_chat_works_without_api_key() -> None:
    shield = AgentShield(mode="shadow")
    chat = ShieldChat(shield)
    resp = asyncio.run(chat.ask("give me a summary"))
    assert resp.answer
    assert resp.mode == "basic"
    assert isinstance(resp.follow_up_suggestions, list)


def test_smart_chat_falls_back_when_no_key() -> None:
    """SmartChat with no API key never calls Claude; returns basic analysis."""
    shield = AgentShield(mode="shadow")
    chat = SmartChat(shield, api_key="")
    assert chat.has_llm is False
    resp = asyncio.run(chat.ask("should I deploy this agent to production without review?"))
    assert resp.mode == "basic"
    assert resp.answer


def test_needs_llm_detection() -> None:
    shield = AgentShield(mode="shadow")
    chat = SmartChat(shield, api_key="sk-ant-test-dummy")
    assert chat.has_llm is True
    assert chat._needs_llm("compare agent behavior trends this week") is True
    assert chat._needs_llm("predict what will happen if we loosen policy") is True
    assert chat._needs_llm("help me understand the risk scores") is True
    assert chat._needs_llm("give me a summary") is False
    assert chat._needs_llm("why blocked") is False
