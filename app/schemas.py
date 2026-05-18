# =============================================================================
# VerdaMap — Pydantic Schemas
# =============================================================================
# Pydantic models define the shape of data coming IN (requests) and
# going OUT (responses). FastAPI uses these for automatic validation
# and OpenAPI documentation.
# =============================================================================

from pydantic import BaseModel, field_validator
from typing import List
from datetime import date


# =============================================================================
# REQUEST SCHEMAS (data coming in from the frontend)
# =============================================================================

class AnalyzeRequest(BaseModel):
    """
    Body of POST /api/analyze

    polygon: list of [lon, lat] pairs forming a closed polygon
             The last point must equal the first (GeoJSON convention).
    date_from / date_to: the date range to search for imagery in.
    """
    polygon: List[List[float]]
    date_from: str   # YYYY-MM-DD
    date_to: str     # YYYY-MM-DD

    @field_validator("polygon")
    @classmethod
    def validate_polygon(cls, v):
        if len(v) < 4:
            raise ValueError("Polygon must have at least 3 points (4 coordinates including closing point).")
        if len(v) > 501:
            raise ValueError("Polygon is too complex. Maximum 500 vertices.")
        for point in v:
            if len(point) != 2:
                raise ValueError("Each polygon point must be [longitude, latitude].")
            lon, lat = point
            if not (-180 <= lon <= 180):
                raise ValueError(f"Longitude {lon} is out of range [-180, 180].")
            if not (-90 <= lat <= 90):
                raise ValueError(f"Latitude {lat} is out of range [-90, 90].")
        return v

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v):
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD.")
        return v


# =============================================================================
# RESPONSE SCHEMAS (data going out to the frontend)
# =============================================================================

class HealthPercentage(BaseModel):
    healthy: float
    moderate: float
    stressed: float
    sparse: float
    no_vegetation: float


class AnalysisResponse(BaseModel):
    """Full analysis result returned by POST /api/analyze and GET /api/analysis/{id}"""
    id: str
    created_at: str
    polygon: List[List[float]]
    date_from: str
    date_to: str
    date_acquired: str
    ndvi_mean: float
    ndvi_min: float
    ndvi_max: float
    ndvi_std: float
    health_status: str
    health_percentage: HealthPercentage
    area_km2: float
    cloud_cover: float
    bbox: List[float]
    image_url: str


class AnalysisListItem(BaseModel):
    """Compact summary used in GET /api/history"""
    id: str
    created_at: str
    date_acquired: str
    ndvi_mean: float
    health_status: str
    area_km2: float
    cloud_cover: float
    bbox: List[float]


class HistoryResponse(BaseModel):
    items: List[AnalysisListItem]
    total: int


class HealthCheckResponse(BaseModel):
    status: str
    version: str
