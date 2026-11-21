"""Request-scoped sessions; no schema creation during API startup."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


def normalize_database_url(url: str) -> str:
    if url.startswith(("postgres://", "postgresql://")):
        return "postgresql+asyncpg://" + url.split("://", 1)[1]
    return url


@lru_cache(maxsize=1)
def get_engine():
    options = {"poolclass": NullPool} if get_settings().TESTING else {"pool_size": 5, "max_overflow": 5}
    return create_async_engine(
        normalize_database_url(get_settings().DATABASE_URL.get_secret_value()),
        **options,
        pool_pre_ping=True,
        hide_parameters=True,
    )


async def get_db_session():
    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
