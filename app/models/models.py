from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Base class all ORM models inherit from.
    pass


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    locations: Mapped[list["GPSLocation"]] = relationship(back_populates="device")
    heartbeats: Mapped[list["TrackerHeartbeat"]] = relationship(back_populates="device")


class GPSLocation(Base):
    __tablename__ = "gps_locations"
    __table_args__ = (
        # Prevent exact duplicate points from same device timestamp.
        UniqueConstraint("device_id", "timestamp", name="uq_device_timestamp"),
        # GeoAlchemy creates the spatial index; the uniqueness constraint indexes history.
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("devices.device_id"),
        nullable=False,
    )

    # PostGIS point column stores true geography coordinates.
    location = mapped_column(Geometry("POINT", srid=4326), nullable=False)

    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    speed: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)

    # Optional GPS quality fields from hardware
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    course: Mapped[float | None] = mapped_column(Float, nullable=True)  # Direction in degrees (0-360)
    satellites: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Number of satellites in view
    fix_status: Mapped[int] = mapped_column(Integer, default=0)  # 0=no lock, 1=valid lock
    last_error: Mapped[str] = mapped_column(String(64), default="NONE")
    last_stage: Mapped[str] = mapped_column(String(64), default="BOOT")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    device: Mapped[Device] = relationship(back_populates="locations")


class TrackerHeartbeat(Base):
    __tablename__ = "tracker_heartbeats"
    __table_args__ = (UniqueConstraint("device_id", "timestamp", name="uq_heartbeat_device_timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("devices.device_id"),
        nullable=False,
    )
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uptime_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fix_status: Mapped[int] = mapped_column(Integer, default=0)
    satellites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modem_responsive: Mapped[bool] = mapped_column(Boolean, default=False)
    network_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    socket_open: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str] = mapped_column(String(64), default="NONE")
    last_stage: Mapped[str] = mapped_column(String(64), default="BOOT")
    consecutive_send_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    device: Mapped[Device] = relationship(back_populates="heartbeats")
