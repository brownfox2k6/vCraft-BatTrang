"""Integration tests for HTTP GET /api/health against PostgreSQL 19."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoint_reports_ok_when_database_is_reachable(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "data": {
            "status": "ok",
            "database": "ok",
        },
        "meta": {},
        "error": None,
    }


def test_health_endpoint_returns_503_when_database_is_unreachable() -> None:
    unreachable_settings = Settings(
        database_url="postgresql+psycopg://vcraft:vcraft@127.0.0.1:1/vcraft_test?connect_timeout=1",
    )
    app = create_app(settings=unreachable_settings)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["data"] is None
    assert payload["meta"] == {}
    assert payload["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"] != ""
