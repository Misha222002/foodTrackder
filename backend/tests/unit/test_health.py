from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from food_tracker.core.config import Settings
from food_tracker.db.session import get_session
from food_tracker.main import create_app


@pytest.mark.anyio
@pytest.mark.parametrize("database_available", [True, False])
async def test_health_contract(database_available):
    session = AsyncMock()
    if not database_available:
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret DSN"))
    app = create_app(Settings(mail_worker_enabled=False))
    app.dependency_overrides[get_session] = lambda: session
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/v1/health")
        UUID(response.headers["X-Request-ID"])
        if database_available:
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "database": "ok"}
        else:
            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "DATABASE_UNAVAILABLE"
            assert body["requestId"] == response.headers["X-Request-ID"]
            assert body["details"] == {}
            assert "secret" not in response.text
        session.execute.assert_awaited_once()


def test_openapi_exposes_success_and_error_without_database():
    schema = create_app(Settings(mail_worker_enabled=False)).openapi()
    operation = schema["paths"]["/api/v1/health"]["get"]
    assert operation["operationId"] == "get_health"
    assert set(operation["responses"]) == {"200", "503"}
    assert schema["components"]["schemas"]["HealthResponse"]["required"] == ["status", "database"]


def test_configuration_accepts_only_selected_postgres_driver(monkeypatch):
    monkeypatch.setenv("FOOD_TRACKER_DATABASE_URL", "postgresql://localhost/test")
    with pytest.raises(ValueError, match="postgresql\\+psycopg"):
        Settings(_env_file=None)
