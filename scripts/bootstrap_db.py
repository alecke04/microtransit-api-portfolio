"""Explicit schema creation, restricted to a named local demo database."""

import asyncio

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.database import get_engine
from app.models.models import Base


async def main():
    settings = get_settings()
    settings.validate_required()
    url = make_url(settings.DATABASE_URL.get_secret_value())
    if url.host not in {"localhost", "127.0.0.1", "::1"} or url.database != "portfolio_demo":
        raise SystemExit("Bootstrap is restricted to the local portfolio_demo database")
    engine = get_engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    print("Local demo schema is ready.")


if __name__ == "__main__":
    asyncio.run(main())
