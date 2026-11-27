import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from food_tracker.core.config import Settings
from food_tracker.db.base import Base
from food_tracker.modules.auth import models as auth_models  # noqa: F401
from food_tracker.modules.users import models as user_models  # noqa: F401


def configure(connection=None):
    context.configure(
        connection=connection,
        url=str(Settings().database_url),
        target_metadata=Base.metadata,
        literal_binds=connection is None,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def migrate():
    engine = create_async_engine(str(Settings().database_url), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    configure()
else:
    asyncio.run(migrate())
