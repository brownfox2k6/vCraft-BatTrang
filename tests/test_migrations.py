"""Integration tests for Alembic migration upgrade/downgrade lifecycle on PostgreSQL 19."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _current_db_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision()
    finally:
        engine.dispose()


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def test_alembic_upgrade_downgrade_upgrade_cycle(
    test_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    expected_head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
    assert expected_head is not None

    command.upgrade(alembic_cfg, "head")
    assert _current_db_revision(test_database_url) == expected_head
    assert {"users", "user_sessions", "login_attempts"}.issubset(_table_names(test_database_url))

    command.downgrade(alembic_cfg, "base")
    assert _current_db_revision(test_database_url) is None
    assert _table_names(test_database_url).isdisjoint({"users", "user_sessions", "login_attempts"})

    command.upgrade(alembic_cfg, "head")
    assert _current_db_revision(test_database_url) == expected_head
    assert {"users", "user_sessions", "login_attempts"}.issubset(_table_names(test_database_url))
