# =============================================================================
# VerdaMap — Database Models
# =============================================================================
# SQLAlchemy ORM models — each class maps to a PostgreSQL table.
# =============================================================================

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Analysis(Base):
    """
    Stores every NDVI analysis that has been run.
    One row = one analysis request from a user.
    """
    __tablename__ = "analyses"

    # Primary key — UUID so IDs are not guessable
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # When the analysis was created (server time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    # ── Input parameters ─────────────────────────────────────────────────────
    # The polygon the user drew, stored as GeoJSON coordinates array
    # e.g. [[lon, lat], [lon, lat], ...]
    polygon: Mapped[list] = mapped_column(JSON, nullable=False)

    # The date range the user requested
    date_from: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    date_to: Mapped[str] = mapped_column(String(10), nullable=False)    # YYYY-MM-DD

    # ── Results ───────────────────────────────────────────────────────────────
    # The actual date of the satellite image used
    date_acquired: Mapped[str] = mapped_column(String(10), nullable=False)

    # NDVI statistics
    ndvi_mean: Mapped[float] = mapped_column(Float, nullable=False)
    ndvi_min: Mapped[float] = mapped_column(Float, nullable=False)
    ndvi_max: Mapped[float] = mapped_column(Float, nullable=False)
    ndvi_std: Mapped[float] = mapped_column(Float, nullable=False)

    # Overall health label derived from ndvi_mean
    health_status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Percentage breakdown by vegetation category (stored as JSON object)
    # e.g. {"healthy": 45.2, "moderate": 30.1, ...}
    health_percentage: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Area of the polygon in km²
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)

    # Cloud cover percentage of the selected image
    cloud_cover: Mapped[float] = mapped_column(Float, nullable=False)

    # Bounding box of the polygon [west, south, east, north]
    bbox: Mapped[list] = mapped_column(JSON, nullable=False)

    # URL of the rendered NDVI color image (served from our backend)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)

    def to_dict(self) -> dict:
        """Convert model to a plain dict for JSON serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "polygon": self.polygon,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "date_acquired": self.date_acquired,
            "ndvi_mean": self.ndvi_mean,
            "ndvi_min": self.ndvi_min,
            "ndvi_max": self.ndvi_max,
            "ndvi_std": self.ndvi_std,
            "health_status": self.health_status,
            "health_percentage": self.health_percentage,
            "area_km2": self.area_km2,
            "cloud_cover": self.cloud_cover,
            "bbox": self.bbox,
            "image_url": self.image_url,
        }
