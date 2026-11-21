"""Separate device-write and reader permissions, with bounded abuse state."""

import hashlib
import hmac
import time
from collections import OrderedDict, deque
from threading import Lock

from fastapi import Header, HTTPException, Request

from app.config import get_settings


def matches(expected: str, provided: str) -> bool:
    # Fixed-length digest comparison avoids differing input lengths in compare_digest.
    return bool(expected and provided) and hmac.compare_digest(
        hashlib.sha256(expected.encode()).digest(), hashlib.sha256(provided.encode()).digest()
    )


def verify_device(device: str, provided: str) -> None:
    if not matches(get_settings().device_keys().get(device, ""), provided):
        raise HTTPException(401, "Invalid or missing device credential")


async def write_credential(x_api_key: str = Header(default="")) -> str:
    return x_api_key


async def read_credential(x_api_key: str = Header(default="")) -> None:
    if not matches(get_settings().READ_API_KEY.get_secret_value(), x_api_key):
        raise HTTPException(401, "Invalid or missing read credential")


class WindowLimiter:
    def __init__(self, maximum: int, window: float = 60, buckets: int = 2000):
        self.maximum, self.window, self.buckets = maximum, window, buckets
        self.entries: OrderedDict[str, deque[float]] = OrderedDict()
        self.lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            queue = self.entries.setdefault(key, deque())
            self.entries.move_to_end(key)
            while len(self.entries) > self.buckets:
                self.entries.popitem(last=False)
            while queue and queue[0] <= now - self.window:
                queue.popleft()
            if len(queue) >= self.maximum:
                return False
            queue.append(now)
            return True


def enforce_ingest_limit(request: Request, device: str) -> None:
    # A single write token covers a device; arbitrary request identifiers never create buckets.
    if not request.app.state.ingest_limiter.allow(device):
        raise HTTPException(429, "Device update rate exceeded")
