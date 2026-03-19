from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentshield.db.models import (
    ActionLog,
    AgentRegistry,
    ApprovalLog,
    ApprovalQueue,
    Base,
    NegotiationLog,
    PolicyHistory,
)

DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./agentshield.db"


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _normalize_url(os.getenv("AGENTSHIELD_DATABASE_URL", DEFAULT_SQLITE_URL))
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def health_check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def log_action(action: Dict[str, Any]) -> None:
    row = ActionLog(
        id=action["id"],
        tool_name=action["tool_name"],
        arguments=action.get("arguments", {}),
        agent_id=action.get("agent_id", "default"),
        decision=action.get("decision", "pending"),
        risk_score=float(action.get("risk_score", 0.0)),
        mode=action.get("mode", "shadow"),
        simulation_result=action.get("simulation_result"),
        rollback_plan=action.get("rollback_plan"),
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()


async def list_actions(
    tool_name: Optional[str] = None,
    decision: Optional[str] = None,
    min_risk: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[ActionLog]:
    query = select(ActionLog).order_by(ActionLog.timestamp.desc())
    if tool_name:
        query = query.where(ActionLog.tool_name == tool_name)
    if decision:
        query = query.where(ActionLog.decision == decision)
    if min_risk is not None:
        query = query.where(ActionLog.risk_score >= min_risk)
    query = query.limit(limit).offset(offset)

    async with get_session() as session:
        result = await session.execute(query)
        return list(result.scalars().all())


async def add_policy_history(policy_yaml: str, applied_by: str = "system") -> str:
    policy_id = str(uuid.uuid4())
    row = PolicyHistory(id=policy_id, policy_yaml=policy_yaml, applied_by=applied_by)
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return policy_id


async def add_approval_log(
    action_id: str,
    approved: bool,
    reason: str = "",
    approved_by: str = "system",
) -> str:
    approval_id = str(uuid.uuid4())
    row = ApprovalLog(
        id=approval_id,
        action_id=action_id,
        approved=approved,
        reason=reason,
        approved_by=approved_by,
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return approval_id


async def add_negotiation_log(
    action_id: str,
    agent_id: str,
    status: str,
    explanation: Dict[str, Any],
    suggestions: List[Dict[str, Any]],
    proposed_safe_action: Optional[Dict[str, Any]] = None,
) -> str:
    negotiation_id = str(uuid.uuid4())
    row = NegotiationLog(
        id=negotiation_id,
        action_id=action_id,
        agent_id=agent_id,
        status=status,
        explanation=explanation,
        suggestions=suggestions,
        proposed_safe_action=proposed_safe_action or {},
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return negotiation_id


async def list_negotiations(limit: int = 200, offset: int = 0) -> List[NegotiationLog]:
    query = select(NegotiationLog).order_by(NegotiationLog.timestamp.desc()).limit(limit).offset(offset)
    async with get_session() as session:
        result = await session.execute(query)
        return list(result.scalars().all())


async def enqueue_approval(action_id: str, requested_by: str, reason: str = "") -> str:
    queue_id = str(uuid.uuid4())
    row = ApprovalQueue(
        id=queue_id,
        action_id=action_id,
        requested_by=requested_by,
        reason=reason,
        status="pending",
    )
    async with get_session() as session:
        session.add(row)
        await session.commit()
    return queue_id


async def touch_agent_registry(agent_id: str) -> None:
    async with get_session() as session:
        result = await session.execute(select(AgentRegistry).where(AgentRegistry.agent_id == agent_id))
        row = result.scalar_one_or_none()
        if row is None:
            row = AgentRegistry(id=str(uuid.uuid4()), agent_id=agent_id, reputation_score=0.5, actions_count=1)
            session.add(row)
        else:
            row.actions_count += 1
        await session.commit()


def alembic_migration_note() -> str:
    return (
        "Alembic-ready SQLAlchemy metadata is available at agentshield.db.models.Base. "
        "Run: alembic init alembic && configure sqlalchemy.url to AGENTSHIELD_DATABASE_URL."
    )
