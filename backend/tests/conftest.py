import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def migrated_database_url():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL server with CREATEDB")
    parsed = make_url(admin_url)
    database_name = f"food_tracker_test_{uuid4().hex}"
    admin_dsn = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
    database_url = parsed.set(database=database_name, drivername="postgresql+psycopg")
    target_url = database_url.render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:

        def migrate(revision):
            subprocess.run(
                [str(BACKEND / ".venv/bin/alembic"), *revision],
                cwd=BACKEND,
                env={**os.environ, "FOOD_TRACKER_DATABASE_URL": target_url},
                check=True,
                capture_output=True,
                text=True,
            )

        migrate(["upgrade", "head"])
        yield target_url, migrate
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )
