import json
import os
import secrets
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

READER, WRITER, SECOND = (secrets.token_urlsafe(32) for _ in range(3))
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/portfolio_test"
)
os.environ["READ_API_KEY"] = READER
os.environ["VALID_API_KEYS_JSON"] = json.dumps({"DEMO_TRACKER_01": WRITER, "DEMO_TRACKER_02": SECOND})
os.environ["INGEST_MIN_INTERVAL_SECONDS"] = "0"

from app.database import get_db_session  # noqa: E402
from main import create_app  # noqa: E402


@pytest.fixture
def keys():
    return {"reader": READER, "writer": WRITER, "second": SECOND}


@pytest.fixture
def session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(session):
    app = create_app()

    async def fake_session():
        yield session

    app.dependency_overrides[get_db_session] = fake_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def point():
    return {
        "device_id": "DEMO_TRACKER_01",
        "latitude": 0.01,
        "longitude": 0.02,
        "timestamp": 1800000000000,
        "speed": 2,
        "accuracy": 3,
        "fix_status": 1,
    }
