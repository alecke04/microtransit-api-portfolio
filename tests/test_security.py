import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.config import Settings, get_settings
from app.models.schemas import LocationCreate
from app.realtime import ConnectionHub
from app.security import WindowLimiter, matches


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 91),
        ("longitude", -181),
        ("speed", -1),
        ("speed", 251),
        ("accuracy", -1),
        ("satellites", 33),
        ("fix_status", 3),
        ("timestamp", -1),
        ("timestamp", True),
        ("timestamp", "1800000000000"),
        ("timestamp", 5000000000000),
        ("device_id", "' OR 1=1 --"),
        ("device_id", "../other"),
        ("last_stage", "x" * 65),
        ("latitude", float("nan")),
        ("speed", float("inf")),
        ("unexpected", "value"),
    ],
)
def test_invalid_points_are_rejected(point, field, value):
    with pytest.raises(ValidationError):
        LocationCreate(**{**point, field: value})


def test_separate_permissions_and_no_sql_for_missing_credentials(client, keys, point, session):
    assert client.post("/api/locations", json=point).status_code == 401
    assert client.post("/api/locations", json=point, headers={"X-API-Key": keys["reader"]}).status_code == 401
    assert client.post("/api/locations", json=point, headers={"X-API-Key": keys["second"]}).status_code == 401
    assert client.get("/api/locations/DEMO_TRACKER_01", headers={"X-API-Key": keys["writer"]}).status_code == 401
    session.execute.assert_not_awaited()


def test_validation_does_not_echo_submitted_secrets(client, keys):
    secret = keys["writer"]
    response = client.post("/api/devices", headers={"X-API-Key": secret}, json={"device_id": "!", "api_key": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_history_limits_and_injection_do_not_reach_database(client, keys, session):
    headers = {"X-API-Key": keys["reader"]}
    for path in [
        "/api/locations/DEMO_TRACKER_01?limit=1001",
        "/api/locations/DEMO_TRACKER_01?start=2&end=1",
        "/api/locations/%27%20OR%201%3D1--",
    ]:
        assert client.get(path, headers=headers).status_code == 422
    session.execute.assert_not_awaited()


def test_body_limit_counts_streamed_bytes(client):
    assert client.post("/api/locations", content=b"x" * 65537).status_code == 413


def test_http_rate_limit_and_bounded_buckets(client):
    client.app.state.http_limiter = WindowLimiter(1, buckets=2)
    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 429
    limiter = WindowLimiter(1, buckets=2)
    for key in ["one", "two", "three"]:
        assert limiter.allow(key)
    assert len(limiter.entries) == 2


def test_cors_exact_origins(client):
    allowed = client.options(
        "/api/locations", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    denied = client.options(
        "/api/locations", headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"}
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    "override",
    [
        {"READ_API_KEY": ""},
        {"VALID_API_KEYS_JSON": "{}"},
        {"CORS_ORIGINS": "*"},
        {"VALID_API_KEYS_JSON": "[]"},
        {"VALID_API_KEYS_JSON": '{"DEMO":"replace-me"}'},
    ],
)
def test_startup_rejects_unsafe_configuration(override):
    settings = Settings(_env_file=None, **override)
    with pytest.raises(ValueError):
        settings.validate_required()


def test_secret_comparison_and_settings_repr(keys):
    assert matches(keys["writer"], keys["writer"])
    assert not matches("", "")
    assert not matches(keys["writer"], keys["reader"])
    assert keys["writer"] not in repr(get_settings())
    assert keys["reader"] not in repr(get_settings())


@pytest.mark.parametrize("payload", [{"type": "auth", "api_key": "invalid"}, [], {"type": "other"}])
def test_socket_rejects_bad_auth_and_releases_slot(client, payload):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
            socket.send_json(payload)
            socket.receive_json()
    assert not client.app.state.hub.connections


def test_socket_origin_unknown_device_and_query_token_are_rejected(client, keys):
    for path, headers in [
        ("/ws/DEMO_TRACKER_01", {"Origin": "https://untrusted.example"}),
        ("/ws/UNKNOWN", {}),
    ]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers=headers):
                pass
    with client.websocket_connect("/ws/DEMO_TRACKER_01?api_key=" + keys["reader"]) as socket:
        socket.send_json({"type": "auth", "api_key": "invalid"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_socket_authentication_limit_and_cleanup(client, keys, monkeypatch):
    monkeypatch.setattr(get_settings(), "WS_MAX_PER_IP", 1)
    with client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
        socket.send_json({"type": "auth", "api_key": keys["reader"]})
        assert socket.receive_json()["type"] == "authenticated"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/DEMO_TRACKER_01"):
                pass
    assert not client.app.state.hub.connections
    assert not client.app.state.hub.authenticated


def test_socket_auth_timeout_frees_capacity(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "WS_AUTH_TIMEOUT_SECONDS", 0.02)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
            socket.receive_json()
    assert not client.app.state.hub.connections


def test_socket_frame_and_commands_are_bounded(client, keys):
    with client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
        socket.send_text("x" * 1025)
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1009
    with client.websocket_connect("/ws/DEMO_TRACKER_01") as socket:
        socket.send_json({"type": "auth", "api_key": keys["reader"]})
        socket.receive_json()
        socket.send_json({"type": "write"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


@pytest.mark.asyncio
async def test_pending_auth_receives_no_data_and_slow_subscriber_is_released(monkeypatch):
    hub = ConnectionHub()
    pending, failed, good = (AsyncMock() for _ in range(3))
    for socket in [pending, failed, good]:
        assert await hub.reserve(socket, "DEMO_TRACKER_01", str(id(socket)))
    hub.authenticated.update([failed, good])
    failed.send_json.side_effect = RuntimeError("closed")
    await hub.broadcast("DEMO_TRACKER_01", {"type": "location_update"})
    pending.send_json.assert_not_awaited()
    good.send_json.assert_awaited_once()
    assert failed not in hub.connections
    assert failed not in hub.authenticated


@pytest.mark.asyncio
async def test_hub_global_limit_is_atomic(monkeypatch):
    monkeypatch.setattr(get_settings(), "WS_MAX_CONNECTIONS", 2)
    hub = ConnectionHub()
    attempts = await asyncio.gather(*(hub.reserve(AsyncMock(), "DEMO_TRACKER_01", str(i)) for i in range(20)))
    assert sum(attempts) == 2
    assert len(hub.connections) == 2
