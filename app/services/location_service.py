from typing import Iterable, List

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GPSLocation
from app.models.schemas import LocationCreate, LocationResponse


def build_location_row(location_data: LocationCreate) -> GPSLocation:
    # Build a geospatial point in WKT form; PostGIS stores this as a real geometry type.
    point = WKTElement(
        f"POINT({location_data.longitude} {location_data.latitude})",
        srid=4326,
    )

    return GPSLocation(
        device_id=location_data.device_id,
        location=point,
        timestamp=location_data.timestamp,
        speed=location_data.speed,
        accuracy=location_data.accuracy,
        altitude=location_data.altitude,
        course=location_data.course,
        satellites=location_data.satellites,
        fix_status=location_data.fix_status,
        last_error=location_data.last_error,
        last_stage=location_data.last_stage,
    )


async def create_location(session: AsyncSession, location_data: LocationCreate) -> GPSLocation:
    db_row = build_location_row(location_data)
    try:
        session.add(db_row)
        await session.commit()
        await session.refresh(db_row)
        return db_row
    except Exception:
        await session.rollback()
        raise


async def create_locations_batch(session: AsyncSession, locations: Iterable[LocationCreate]) -> int:
    """Persist a burst upload atomically without one transaction per point."""
    rows = [build_location_row(location) for location in locations]
    try:
        session.add_all(rows)
        await session.commit()
        return len(rows)
    except Exception:
        await session.rollback()
        raise


def to_response(row: GPSLocation) -> LocationResponse:
    # Convert DB geometry into plain lat/lon numbers for JSON output.
    point = to_shape(row.location)
    return LocationResponse(
        id=row.id,
        device_id=row.device_id,
        latitude=point.y,
        longitude=point.x,
        speed=row.speed,
        accuracy=row.accuracy,
        timestamp=row.timestamp,
        created_at=row.created_at,
        altitude=row.altitude,
        course=row.course,
        satellites=row.satellites,
        fix_status=row.fix_status,
        last_error=row.last_error,
        last_stage=row.last_stage,
    )


async def get_locations_by_device(
    session: AsyncSession,
    device_id: str,
    limit: int = 100,
    start_timestamp: int | None = None,
    end_timestamp: int | None = None,
) -> List[LocationResponse]:
    statement = select(GPSLocation).where(GPSLocation.device_id == device_id)

    if start_timestamp is not None:
        statement = statement.where(GPSLocation.timestamp >= start_timestamp)

    if end_timestamp is not None:
        statement = statement.where(GPSLocation.timestamp <= end_timestamp)

    statement = statement.order_by(GPSLocation.timestamp.desc()).limit(limit)
    rows = (await session.execute(statement)).scalars().all()
    return [to_response(row) for row in rows]
