"""Runs against the disposable PostGIS service in CI, never against production."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.database import get_engine
from app.models.models import Base
from main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def db_client(keys):
    configured = os.getenv("TEST_DATABASE_URL")
    if not configured:
        pytest.skip("Set TEST_DATABASE_URL to the disposable local portfolio_test database")
    url = make_url(configured)
    assert url.database == "portfolio_test" and url.host in {"localhost", "127.0.0.1", "::1"}

    async def setup():
        async with get_engine().begin() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/devices",
            headers={"X-API-Key": keys["writer"]},
            json={"device_id": "DEMO_TRACKER_01", "api_key": keys["writer"], "team_name": "Synthetic integration test"},
        )
        assert response.status_code == 201, response.text
        assert keys["writer"] not in response.text
        yield client


def test_postgis_round_trip_broadcast_and_duplicate_recovery(db_client, keys, point):
    with db_client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
        socket.send_json({"type": "auth", "api_key": keys["reader"]})
        assert socket.receive_json()["type"] == "authenticated"
        saved = db_client.post("/api/locations", json=point, headers={"X-API-Key": keys["writer"]})
        assert saved.status_code == 201
        assert socket.receive_json()["latitude"] == point["latitude"]
    duplicate = db_client.post("/api/locations", json=point, headers={"X-API-Key": keys["writer"]})
    assert duplicate.status_code == 409
    history = db_client.get("/api/locations/DEMO_TRACKER_01", headers={"X-API-Key": keys["reader"]})
    assert history.status_code == 200
    rows = history.json()["locations"]
    assert len(rows) == 1
    assert rows[0]["latitude"] == point["latitude"]
    assert rows[0]["longitude"] == point["longitude"]


def test_failed_batch_is_atomic(db_client, keys, point):
    headers = {"X-API-Key": keys["writer"]}
    assert db_client.post("/api/locations", json=point, headers=headers).status_code == 201
    batch = {"device_id": point["device_id"], "locations": [{**point, "timestamp": point["timestamp"] - 1}, point]}
    assert db_client.post("/api/locations/batch", json=batch, headers=headers).status_code == 409
    history = db_client.get("/api/locations/DEMO_TRACKER_01", headers={"X-API-Key": keys["reader"]})
    assert history.json()["count"] == 1


def test_heartbeat_persists_and_duplicate_is_rejected(db_client, keys):
    payload = {"device_id": "DEMO_TRACKER_01", "timestamp": 1800000000000, "fix_status": 1, "network_ready": True}
    headers = {"X-API-Key": keys["writer"]}
    assert db_client.post("/api/heartbeats", json=payload, headers=headers).status_code == 201
    assert db_client.post("/api/heartbeats", json=payload, headers=headers).status_code == 409
    response = db_client.get("/api/heartbeats/DEMO_TRACKER_01/history", headers={"X-API-Key": keys["reader"]})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["heartbeats"][0]["network_ready"] is True


def test_history_query_uses_device_timestamp_index_with_10000_points(db_client):
    async def check_plan():
        async with get_engine().begin() as connection:
            await connection.execute(
                text("""
                INSERT INTO gps_locations (device_id, location, timestamp, speed, accuracy, fix_status, last_error, last_stage, created_at)
                SELECT 'DEMO_TRACKER_01', ST_SetSRID(ST_MakePoint(0.02, 0.01), 4326), n, 0, 0, 1, 'NONE', 'SYNTHETIC', NOW()
                FROM generate_series(1, 10000) AS n
            """)
            )
            await connection.execute(text("ANALYZE gps_locations"))
            result = await connection.execute(
                text("""
                EXPLAIN (ANALYZE, FORMAT JSON, TIMING FALSE)
                SELECT * FROM gps_locations WHERE device_id = 'DEMO_TRACKER_01' ORDER BY timestamp DESC LIMIT 25
            """)
            )
            report = result.scalar_one()[0]
            plan = report["Plan"]
            assert plan["Node Type"] == "Limit" and plan["Actual Rows"] == 25
            assert "uq_device_timestamp" in str(plan)
            assert report["Execution Time"] < 1000

    asyncio.run(check_plan())
