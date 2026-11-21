import time
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LocationCreate(PublicModel):
    # This is the exact payload shape expected from Arduino/API clients.
    device_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed: float = Field(default=0, ge=0, le=250)
    accuracy: float = Field(default=0, ge=0, le=10000)
    # Default lets backend accept payloads even if device forgot to include timestamp.
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), ge=0, le=4102444800000, strict=True)
    # Optional GPS quality fields from hardware (SIM7000 module)
    altitude: Optional[float] = Field(default=None, ge=-500, le=10000)  # meters
    course: Optional[float] = Field(default=None, ge=0, le=360)  # degrees
    satellites: Optional[int] = Field(default=None, ge=0, le=32)  # count
    fix_status: int = Field(default=0, ge=0, le=1)  # 0=no lock, 1=valid lock
    last_error: str = Field(default="NONE", min_length=1, max_length=64)
    last_stage: str = Field(default="BOOT", min_length=1, max_length=64)


class LocationResponse(PublicModel):
    # Output model for API reads. Kept separate from DB model on purpose.
    id: int
    device_id: str
    latitude: float
    longitude: float
    speed: float
    accuracy: float
    timestamp: int
    created_at: datetime
    # Optional GPS quality fields
    altitude: Optional[float] = None
    course: Optional[float] = None
    satellites: Optional[int] = None
    fix_status: int = 0
    last_error: str = "NONE"
    last_stage: str = "BOOT"


class HeartbeatCreate(PublicModel):
    device_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    # Event time in Unix epoch milliseconds. Device uptime belongs in uptime_ms.
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), ge=0, le=4102444800000, strict=True)
    uptime_ms: Optional[int] = Field(default=None, ge=0)
    fix_status: int = Field(default=0, ge=0, le=1)
    satellites: Optional[int] = Field(default=None, ge=0, le=32)
    modem_responsive: bool = Field(default=False)
    network_ready: bool = Field(default=False)
    ip_ready: bool = Field(default=False)
    socket_open: bool = Field(default=False)
    last_error: str = Field(default="NONE", min_length=1, max_length=64)
    last_stage: str = Field(default="BOOT", min_length=1, max_length=64)
    consecutive_send_failures: int = Field(default=0, ge=0, le=100)


class HeartbeatResponse(PublicModel):
    device_id: str
    received_at: datetime
    timestamp: int
    uptime_ms: Optional[int] = None
    fix_status: int = 0
    satellites: Optional[int] = None
    modem_responsive: bool = False
    network_ready: bool = False
    ip_ready: bool = False
    socket_open: bool = False
    last_error: str = "NONE"
    last_stage: str = "BOOT"
    consecutive_send_failures: int = 0


class HeartbeatListResponse(PublicModel):
    count: int
    has_more: bool
    heartbeats: list[HeartbeatResponse]


class LocationCreateResponse(PublicModel):
    status: str
    location_id: int


class BatchLocationCreate(PublicModel):
    device_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    locations: list[LocationCreate] = Field(..., min_length=1, max_length=100)


class BatchLocationCreateResponse(PublicModel):
    status: str
    inserted: int


class LocationListResponse(PublicModel):
    count: int
    has_more: bool
    locations: list[LocationResponse]


class DeviceCreate(PublicModel):
    device_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    team_name: Optional[str] = Field(default=None, max_length=255)
    api_key: SecretStr = Field(..., min_length=32, max_length=256)


class DeviceResponse(PublicModel):
    id: int
    device_id: str
    team_name: Optional[str]
    created_at: datetime
