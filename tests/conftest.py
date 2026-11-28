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
from app.models.audit import AuditLog
from app.models.auth import LoginAttempt, User, UserSession
from app.models.media import MediaAsset
from app.models.workshop import WorkshopApplication

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CsrfTestClient(TestClient):
    """TestClient that optionally attaches the active vcraft_csrf cookie as X-CSRF-Token."""

    def __init__(
        self,
        *args: Any,
        auto_csrf: bool = True,
        csrf_cookie_name: str = "vcraft_csrf",
        csrf_header_name: str = "X-CSRF-Token",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._auto_csrf = auto_csrf
        self._csrf_cookie_name = csrf_cookie_name
        self._csrf_header_name = csrf_header_name

    def request(self, method: str, url: Any, **kwargs: Any) -> Any:
        if self._auto_csrf and method.upper() in _MUTATING_METHODS:
            headers = dict(kwargs.get("headers") or {})
            has_header = any(k.lower() == self._csrf_header_name.lower() for k in headers)
            data = kwargs.get("data")
            has_form_token = isinstance(data, dict) and "_csrf_token" in data
            if not has_header and not has_form_token:
                token = self.cookies.get(self._csrf_cookie_name)
                if not token:
                    super().request("GET", "/")
                    token = self.cookies.get(self._csrf_cookie_name)
                if token:
                    headers[self._csrf_header_name] = token
                    is_secure_csrf = any(
                        c.name == self._csrf_cookie_name and c.secure for c in self.cookies.jar
                    )
                    if is_secure_csrf and str(self.base_url).startswith("http://"):
                        pairs = [f"{c.name}={c.value}" for c in self.cookies.jar]
                        existing_cookie = headers.get("Cookie", "")
                        if existing_cookie:
                            pairs.insert(0, existing_cookie)
                        headers["Cookie"] = "; ".join(pairs)
                    kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


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
        auto_csrf: bool = True,
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
    """Clean auth and audit tables before each test without holding open DB connections."""
    engine = create_engine(migrated_test_db)
    try:
        with engine.begin() as connection:
            connection.execute(delete(WorkshopApplication))
            connection.execute(delete(MediaAsset))
            connection.execute(delete(AuditLog))
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
    with CsrfTestClient(
        app,
        csrf_cookie_name=settings.csrf_cookie_name,
        csrf_header_name=settings.csrf_header_name,
    ) as test_client:
        yield test_client


@pytest.fixture()
def make_client(clean_auth_db: str) -> ClientFactory:
    """Build isolated TestClient instances backed by the clean test database."""

    @contextmanager
    def _factory(
        *,
        base_url: str = "http://testserver",
        clock: Callable[[], datetime] | None = None,
        auto_csrf: bool = True,
        **settings_overrides: Any,
    ) -> Iterator[TestClient]:
        settings = Settings(database_url=clean_auth_db, **settings_overrides)
        app = create_app(settings=settings, clock=clock)
        with CsrfTestClient(
            app,
            base_url=base_url,
            auto_csrf=auto_csrf,
            csrf_cookie_name=settings.csrf_cookie_name,
            csrf_header_name=settings.csrf_header_name,
        ) as test_client:
            yield test_client

    return _factory


@pytest.fixture()
def auth_client(clean_auth_db: str) -> Iterator[TestClient]:
    """Provide a TestClient with clean auth and audit tables for integration tests."""
    settings = Settings(database_url=clean_auth_db)
    app = create_app(settings=settings)
    with CsrfTestClient(
        app,
        csrf_cookie_name=settings.csrf_cookie_name,
        csrf_header_name=settings.csrf_header_name,
    ) as test_client:
        yield test_client
