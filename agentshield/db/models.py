from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    tool_name: Mapped[str] = mapped_column(String(256), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    mode: Mapped[str] = mapped_column(String(32))
    simulation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rollback_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PolicyHistory(Base):
    __tablename__ = "policy_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    policy_yaml: Mapped[str] = mapped_column(Text)
    applied_by: Mapped[str] = mapped_column(String(128), default="system")


class ApprovalLog(Base):
    __tablename__ = "approval_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(64), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[str] = mapped_column(String(128), default="system")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class NegotiationLog(Base):
    __tablename__ = "negotiation_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="negotiating")
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    suggestions: Mapped[dict] = mapped_column(JSON, default=list)
    proposed_safe_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ApprovalQueue(Base):
    __tablename__ = "approval_queue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(64), index=True)
    requested_by: Mapped[str] = mapped_column(String(128), default="agent")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    reputation_score: Mapped[float] = mapped_column(Float, default=0.5)
    actions_count: Mapped[int] = mapped_column(default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
