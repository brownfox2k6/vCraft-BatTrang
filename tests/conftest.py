"""Shared pytest fixtures wired to the isolated PostgreSQL 19 test database."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import Settings
from app.main import create_app


class _TestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    test_database_url: str = "postgresql+psycopg://vcraft:vcraft@localhost:5432/vcraft_test"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _TestSettings().test_database_url


@pytest.fixture()
def client(test_database_url: str) -> Iterator[TestClient]:
    settings = Settings(database_url=test_database_url)
    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client
