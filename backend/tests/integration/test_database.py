import psycopg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from food_tracker.core.config import Settings
from food_tracker.main import create_app


@pytest.mark.anyio
async def test_migrations_and_real_api(migrated_database_url):
    database_url, migrate = migrated_database_url
    dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0002_accounts",
        )
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        assert {name for (name,) in tables} == {
            "alembic_version",
            "users",
            "auth_sessions",
            "refresh_tokens",
            "email_challenges",
            "auth_rate_limits",
            "email_outbox",
        }
    migrate(["upgrade", "head"])
    migrate(["check"])
    migrate(["downgrade", "base"])
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == []
    migrate(["upgrade", "head"])
    app = create_app(Settings(database_url=database_url, mail_worker_enabled=False))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.anyio
async def test_real_unavailable_database_returns_503():
    config = Settings(
        database_url="postgresql+psycopg://unused:unused@127.0.0.1:1/unavailable",
        mail_worker_enabled=False,
    )
    app = create_app(config)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
