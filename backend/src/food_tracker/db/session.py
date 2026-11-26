from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from food_tracker.core.config import Settings


def create_engine(settings: Settings):
    return create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
