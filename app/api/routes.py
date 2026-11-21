"""Core registration, write and bounded history endpoints from the tracker architecture."""

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.models import Device, TrackerHeartbeat
from app.models.schemas import (
    BatchLocationCreate,
    BatchLocationCreateResponse,
    DeviceCreate,
    DeviceResponse,
    HeartbeatCreate,
    HeartbeatListResponse,
    HeartbeatResponse,
    LocationCreate,
    LocationCreateResponse,
    LocationListResponse,
)
from app.security import enforce_ingest_limit, matches, read_credential, verify_device, write_credential
from app.services.location_service import create_location, create_locations_batch, get_locations_by_device

router = APIRouter()
DEVICE_PATTERN = r"^[A-Za-z0-9_-]{1,50}$"


async def registered(session: AsyncSession, device: str) -> Device:
    result = await session.execute(select(Device).where(Device.device_id == device))
    model = result.scalars().first()
    if model is None:
        raise HTTPException(404, "Device is not registered")
    return model


@router.post("/api/devices", response_model=DeviceResponse, status_code=201)
async def create_device(
    payload: DeviceCreate, session: AsyncSession = Depends(get_db_session), credential: str = Depends(write_credential)
):
    verify_device(payload.device_id, credential)
    if not matches(credential, payload.api_key.get_secret_value()):
        raise HTTPException(401, "Device credential mismatch")
    model = Device(
        device_id=payload.device_id,
        team_name=payload.team_name,
        api_key="sha256:" + hashlib.sha256(credential.encode()).hexdigest(),
    )
    try:
        session.add(model)
        await session.commit()
        await session.refresh(model)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Device is already registered") from None
    return DeviceResponse(
        id=model.id, device_id=model.device_id, team_name=model.team_name, created_at=model.created_at
    )


@router.post("/api/locations", response_model=LocationCreateResponse, status_code=201)
async def record_location(
    payload: LocationCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    credential: str = Depends(write_credential),
):
    verify_device(payload.device_id, credential)
    enforce_ingest_limit(request, payload.device_id)
    await registered(session, payload.device_id)
    try:
        model = await create_location(session, payload)
    except IntegrityError:
        raise HTTPException(409, "Device timestamp already exists") from None
    # The database commit precedes notification. Failed subscribers never undo a saved point.
    await request.app.state.hub.broadcast(payload.device_id, {"type": "location_update", **payload.model_dump()})
    return LocationCreateResponse(status="recorded", location_id=model.id)


@router.post("/api/locations/batch", response_model=BatchLocationCreateResponse, status_code=201)
async def record_batch(
    payload: BatchLocationCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    credential: str = Depends(write_credential),
):
    verify_device(payload.device_id, credential)
    if any(item.device_id != payload.device_id for item in payload.locations):
        raise HTTPException(422, "Every point must belong to the authenticated device")
    enforce_ingest_limit(request, payload.device_id)
    await registered(session, payload.device_id)
    try:
        inserted = await create_locations_batch(session, payload.locations)
    except IntegrityError:
        raise HTTPException(409, "Batch contains duplicate device timestamps") from None
    return BatchLocationCreateResponse(status="recorded", inserted=inserted)


@router.get("/api/locations/{device_id}", response_model=LocationListResponse, dependencies=[Depends(read_credential)])
async def history(
    device_id: str = Path(pattern=DEVICE_PATTERN),
    limit: int = Query(default=100, ge=1, le=1000),
    start: int | None = Query(default=None, ge=0),
    end: int | None = Query(default=None, ge=0),
    session: AsyncSession = Depends(get_db_session),
):
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "start must not exceed end")
    rows = await get_locations_by_device(session, device_id, limit, start, end)
    return LocationListResponse(count=len(rows), has_more=len(rows) == limit, locations=rows)


def heartbeat_response(row: TrackerHeartbeat) -> HeartbeatResponse:
    return HeartbeatResponse(
        received_at=row.created_at, **{name: getattr(row, name) for name in HeartbeatCreate.model_fields}
    )


@router.post("/api/heartbeats", response_model=HeartbeatResponse, status_code=201)
async def record_heartbeat(
    payload: HeartbeatCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    credential: str = Depends(write_credential),
):
    verify_device(payload.device_id, credential)
    enforce_ingest_limit(request, payload.device_id)
    await registered(session, payload.device_id)
    row = TrackerHeartbeat(**payload.model_dump())
    try:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Heartbeat timestamp already exists") from None
    return heartbeat_response(row)


@router.get(
    "/api/heartbeats/{device_id}/history", response_model=HeartbeatListResponse, dependencies=[Depends(read_credential)]
)
async def heartbeat_history(
    device_id: str = Path(pattern=DEVICE_PATTERN),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
):
    statement = (
        select(TrackerHeartbeat)
        .where(TrackerHeartbeat.device_id == device_id)
        .order_by(TrackerHeartbeat.timestamp.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return HeartbeatListResponse(
        count=len(rows), has_more=len(rows) == limit, heartbeats=[heartbeat_response(row) for row in rows]
    )
