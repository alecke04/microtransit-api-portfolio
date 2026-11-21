from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy.dialects import postgresql

from app.models.schemas import LocationCreate
from app.services.location_service import create_location, create_locations_batch, get_locations_by_device


@pytest.mark.asyncio
async def test_batch_commits_once_and_rolls_back_on_failure(point):
    session = SimpleNamespace(add_all=MagicMock(), commit=AsyncMock(), rollback=AsyncMock())
    locations = [LocationCreate(**point), LocationCreate(**{**point, "timestamp": point["timestamp"] + 1})]
    assert await create_locations_batch(session, locations) == 2
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.commit.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        await create_locations_batch(session, locations)
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_insert_rolls_back_and_never_returns_success(point):
    session = SimpleNamespace(
        add=MagicMock(),
        commit=AsyncMock(side_effect=RuntimeError("unavailable")),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
    )
    with pytest.raises(RuntimeError):
        await create_location(session, LocationCreate(**point))
    session.rollback.assert_awaited_once()
    session.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_uses_bound_sql_and_limit():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    unsafe = "' OR 1=1 --"
    assert await get_locations_by_device(session, unsafe, 50, 1, 10) == []
    statement = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert unsafe not in str(statement)
    assert unsafe in statement.params.values()
    assert "LIMIT" in str(statement)
    assert "ORDER BY gps_locations.timestamp DESC" in str(statement)


def test_api_broadcasts_only_after_saved_point(client, keys, point, monkeypatch):
    from app.api import routes

    saved = AsyncMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(routes, "registered", AsyncMock())
    monkeypatch.setattr(routes, "create_location", saved)
    broadcast = AsyncMock()
    client.app.state.hub.broadcast = broadcast
    response = client.post("/api/locations", json=point, headers={"X-API-Key": keys["writer"]})
    assert response.status_code == 201
    assert response.json()["location_id"] == 7
    saved.assert_awaited_once()
    broadcast.assert_awaited_once()
    saved.side_effect = RuntimeError("unavailable")
    broadcast.reset_mock()
    assert client.post("/api/locations", json=point, headers={"X-API-Key": keys["writer"]}).status_code == 500
    broadcast.assert_not_awaited()


def test_batch_rejects_cross_device_points_before_sql(client, keys, point, session):
    response = client.post(
        "/api/locations/batch",
        headers={"X-API-Key": keys["writer"]},
        json={"device_id": point["device_id"], "locations": [{**point, "device_id": "DEMO_TRACKER_02"}]},
    )
    assert response.status_code == 422
    session.execute.assert_not_awaited()


def test_history_decodes_postgis_geometry(client, keys, session):
    row = SimpleNamespace(
        id=1,
        device_id="DEMO_TRACKER_01",
        location=WKTElement("POINT(0.02 0.01)", srid=4326),
        speed=2,
        accuracy=3,
        timestamp=1800000000000,
        created_at=datetime.now(timezone.utc),
        altitude=None,
        course=None,
        satellites=None,
        fix_status=1,
        last_error="NONE",
        last_stage="DEMO",
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session.execute.return_value = result
    response = client.get("/api/locations/DEMO_TRACKER_01", headers={"X-API-Key": keys["reader"]})
    assert response.status_code == 200
    assert response.json()["locations"][0]["latitude"] == 0.01
    assert response.json()["locations"][0]["longitude"] == 0.02
