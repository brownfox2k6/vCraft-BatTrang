"""Shared pytest fixtures wired to the isolated PostgreSQL 19 test database."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, delete

from app.core.config import Settings
from app.main import create_app
from app.models.auth import LoginAttempt, User, UserSession

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    test_database_url: str = "postgresql+psycopg://vcraft:vcraft@localhost:5432/vcraft_test"


class MutableClock:
    """Controllable UTC clock for deterministic session expiry and rate-limit tests."""

    def __init__(self, initial: datetime | None = None) -> None:
        self.now = initial or datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: int = 0, minutes: int = 0) -> datetime:
        self.now = self.now + timedelta(seconds=seconds, minutes=minutes)
        return self.now


class ClientFactory(Protocol):
    """Protocol for the make_client pytest fixture."""

    def __call__(
        self,
        *,
        base_url: str = "http://testserver",
        clock: Callable[[], datetime] | None = None,
        **settings_overrides: Any,
    ) -> AbstractContextManager[TestClient]: ...


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _TestSettings().test_database_url


@pytest.fixture(scope="session")
def migrated_test_db(test_database_url: str) -> str:
    """Ensure the isolated test database is migrated to Alembic head once per session."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    try:
        alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
    finally:
        monkeypatch.undo()
    return test_database_url


@pytest.fixture()
def clean_auth_db(migrated_test_db: str) -> str:
    """Clean auth tables before each test without holding open DB connections."""
    engine = create_engine(migrated_test_db)
    try:
        with engine.begin() as connection:
            connection.execute(delete(LoginAttempt))
            connection.execute(delete(UserSession))
            connection.execute(delete(User))
    finally:
        engine.dispose()
    return migrated_test_db


@pytest.fixture()
def client(test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(database_url=test_database_url)
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_client(clean_auth_db: str) -> ClientFactory:
    """Build isolated TestClient instances backed by the clean test database."""

    @contextmanager
    def _factory(
        *,
        base_url: str = "http://testserver",
        clock: Callable[[], datetime] | None = None,
        **settings_overrides: Any,
    ) -> Iterator[TestClient]:
        settings = Settings(database_url=clean_auth_db, **settings_overrides)
        app = create_app(settings=settings, clock=clock)
        with TestClient(app, base_url=base_url) as test_client:
            yield test_client

    return _factory


@pytest.fixture()
def auth_client(clean_auth_db: str) -> Iterator[TestClient]:
    """Provide a TestClient with clean auth tables for integration tests."""
    settings = Settings(database_url=clean_auth_db)
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client
