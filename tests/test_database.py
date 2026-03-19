import asyncio
import importlib
import os
import uuid
from pathlib import Path


def _load_db_module(tmp_path: Path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    os.environ["AGENTSHIELD_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    import agentshield.db.database as database_module

    return importlib.reload(database_module)


def test_init_and_health_check(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())
    assert asyncio.run(db.health_check_db()) is True


def test_log_action_and_list_actions(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())
    asyncio.run(
        db.log_action(
            {
                "id": "a1",
                "tool_name": "send_email",
                "arguments": {"to": "a@b.com"},
                "agent_id": "agent-1",
                "decision": "shadow",
                "risk_score": 0.3,
                "mode": "shadow",
            }
        )
    )
    rows = asyncio.run(db.list_actions(limit=10))
    assert len(rows) == 1
    assert rows[0].tool_name == "send_email"


def test_query_filters(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())
    asyncio.run(
        db.log_action(
            {
                "id": "a1",
                "tool_name": "send_email",
                "arguments": {},
                "agent_id": "a",
                "decision": "shadow",
                "risk_score": 0.2,
                "mode": "shadow",
            }
        )
    )
    asyncio.run(
        db.log_action(
            {
                "id": "a2",
                "tool_name": "create_ticket",
                "arguments": {},
                "agent_id": "b",
                "decision": "block",
                "risk_score": 0.9,
                "mode": "shadow",
            }
        )
    )
    filtered = asyncio.run(db.list_actions(tool_name="create_ticket", decision="block", min_risk=0.8))
    assert len(filtered) == 1
    assert filtered[0].id == "a2"


def test_policy_and_approval_persistence(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())
    policy_id = asyncio.run(db.add_policy_history("version: 1", applied_by="tester"))
    approval_id = asyncio.run(
        db.add_approval_log(action_id="x", approved=True, reason="ok", approved_by="tester")
    )
    assert policy_id
    assert approval_id


def test_concurrent_writes(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())

    async def _write_many():
        await asyncio.gather(
            *[
                db.log_action(
                    {
                        "id": f"id-{i}",
                        "tool_name": "generic_api",
                        "arguments": {"i": i},
                        "agent_id": "concurrent",
                        "decision": "shadow",
                        "risk_score": 0.5,
                        "mode": "shadow",
                    }
                )
                for i in range(30)
            ]
        )

    asyncio.run(_write_many())
    rows = asyncio.run(db.list_actions(limit=100))
    assert len(rows) == 30


def test_pagination_limit_offset(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    asyncio.run(db.init_db())
    for i in range(12):
        asyncio.run(
            db.log_action(
                {
                    "id": f"p-{i}",
                    "tool_name": "api",
                    "arguments": {},
                    "agent_id": "p",
                    "decision": "shadow",
                    "risk_score": 0.1,
                    "mode": "shadow",
                }
            )
        )
    page = asyncio.run(db.list_actions(limit=5, offset=5))
    assert len(page) == 5


def test_alembic_note_exists(tmp_path: Path) -> None:
    db = _load_db_module(tmp_path)
    note = db.alembic_migration_note()
    assert "Alembic-ready" in note
