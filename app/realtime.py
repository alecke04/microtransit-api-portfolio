"""Authenticated, bounded subscriptions; credentials never appear in URLs."""

import asyncio
import json
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.security import matches

router = APIRouter()


class ConnectionHub:
    def __init__(self):
        self.connections: dict[WebSocket, tuple[str, str]] = {}
        self.authenticated: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def reserve(self, socket: WebSocket, device: str, ip: str) -> bool:
        settings = get_settings()
        async with self.lock:
            if len(self.connections) >= settings.WS_MAX_CONNECTIONS:
                return False
            if sum(peer == ip for _, peer in self.connections.values()) >= settings.WS_MAX_PER_IP:
                return False
            self.connections[socket] = (device, ip)
            return True

    def disconnect(self, socket: WebSocket) -> None:
        self.connections.pop(socket, None)
        self.authenticated.discard(socket)

    async def broadcast(self, device: str, payload: dict) -> None:
        async def send(socket):
            try:
                await asyncio.wait_for(socket.send_json(payload), get_settings().WS_SEND_TIMEOUT_SECONDS)
            except Exception:
                self.disconnect(socket)
                try:
                    await asyncio.wait_for(socket.close(code=1013), 1)
                except Exception:
                    pass

        await asyncio.gather(
            *(
                send(socket)
                for socket, (target, _) in list(self.connections.items())
                if target == device and socket in self.authenticated
            )
        )


@router.websocket("/ws/{device_id}")
async def subscribe(socket: WebSocket, device_id: str):
    settings = get_settings()
    hub: ConnectionHub = socket.app.state.hub
    origin = socket.headers.get("origin")
    if (origin and origin.rstrip("/") not in settings.origins()) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", device_id):
        return await socket.close(code=1008)
    if device_id not in settings.device_keys():
        return await socket.close(code=1008)
    ip = socket.client.host if socket.client else "unknown"
    if not socket.app.state.http_limiter.allow("ws:" + ip) or not await hub.reserve(socket, device_id, ip):
        return await socket.close(code=1013)
    try:
        await socket.accept()
        # First-message auth works in browsers without putting a reusable secret in a query string.
        raw = await asyncio.wait_for(socket.receive_text(), settings.WS_AUTH_TIMEOUT_SECONDS)
        if len(raw.encode()) > 1024:
            return await socket.close(code=1009)
        message = json.loads(raw)
        if (
            not isinstance(message, dict)
            or message.get("type") != "auth"
            or not isinstance(message.get("api_key"), str)
        ):
            return await socket.close(code=1008)
        if not matches(settings.READ_API_KEY.get_secret_value(), message["api_key"]):
            return await socket.close(code=1008)
        hub.authenticated.add(socket)
        await socket.send_json({"type": "authenticated", "device_id": device_id})
        # No commands or writes are accepted from subscribers.
        while True:
            try:
                incoming = await asyncio.wait_for(socket.receive_text(), 30)
            except asyncio.TimeoutError:
                await asyncio.wait_for(socket.send_json({"type": "ping"}), settings.WS_SEND_TIMEOUT_SECONDS)
                continue
            if len(incoming.encode()) > 1024:
                return await socket.close(code=1009)
            if incoming != "pong":
                return await socket.close(code=1008)
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
        pass
    finally:
        hub.disconnect(socket)
        try:
            await asyncio.wait_for(socket.close(), 1)
        except Exception:
            pass
