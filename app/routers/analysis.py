# =============================================================================
# VerdaMap — Analysis Router
# =============================================================================
# Handles POST /api/analyze — the main endpoint.
# Orchestrates: Sentinel Hub → image store → database → response.
# =============================================================================

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Analysis
from app.schemas import AnalyzeRequest, AnalysisResponse, AnalysisListItem, HistoryResponse
from app.services.sentinel import sentinel_service, SentinelHubError
from app.services.image_store import save_ndvi_image
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api", tags=["analysis"])


# =============================================================================
# POST /api/analyze
# =============================================================================
@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Run NDVI vegetation analysis",
    description="Accepts a polygon and date range, fetches Sentinel-2 imagery, and returns NDVI statistics.",
)
async def analyze_vegetation(
    request: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
):
    analysis_id = str(uuid.uuid4())

    try:
        # ── Step 1: Get NDVI statistics from Sentinel Hub ─────────────────────
        stats = await sentinel_service.get_ndvi_statistics(
            polygon=request.polygon,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        # ── Step 2: Compute bounding box and area ─────────────────────────────
        bbox = sentinel_service.polygon_to_bbox(request.polygon)
        area_km2 = sentinel_service.polygon_area_km2(request.polygon)

        # ── Step 3: Get the rendered NDVI color image ─────────────────────────
        png_bytes = await sentinel_service.get_ndvi_image(
            polygon=request.polygon,
            bbox=bbox,
            date_acquired=stats["date_acquired"],
        )

        # ── Step 4: Save image to disk, get public URL ────────────────────────
        image_url = save_ndvi_image(png_bytes, analysis_id)

        # Make the URL absolute so the frontend can load it directly
        full_image_url = f"{settings.api_base_url}{image_url}"

        # ── Step 5: Determine health status label ─────────────────────────────
        health_status = sentinel_service.get_health_status(stats["ndvi_mean"])

        # ── Step 6: Persist to database ───────────────────────────────────────
        analysis = Analysis(
            id=analysis_id,
            polygon=request.polygon,
            date_from=request.date_from,
            date_to=request.date_to,
            date_acquired=stats["date_acquired"],
            ndvi_mean=stats["ndvi_mean"],
            ndvi_min=stats["ndvi_min"],
            ndvi_max=stats["ndvi_max"],
            ndvi_std=stats["ndvi_std"],
            health_status=health_status,
            health_percentage=stats["health_percentage"],
            area_km2=round(area_km2, 4),
            cloud_cover=stats["cloud_cover"],
            bbox=bbox,
            image_url=full_image_url,
        )
        db.add(analysis)
        await db.flush()  # write to DB within the transaction

        return analysis.to_dict()

    except SentinelHubError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()  # prints full stack trace to the server console
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}",
        )


# =============================================================================
# GET /api/history
# =============================================================================
@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get analysis history",
    description="Returns the 50 most recent analyses, newest first.",
)
async def get_history(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis)
        .order_by(desc(Analysis.created_at))
        .limit(50)
    )
    analyses = result.scalars().all()

    items = [
        AnalysisListItem(
            id=a.id,
            created_at=a.created_at.isoformat(),
            date_acquired=a.date_acquired,
            ndvi_mean=a.ndvi_mean,
            health_status=a.health_status,
            area_km2=a.area_km2,
            cloud_cover=a.cloud_cover,
            bbox=a.bbox,
        )
        for a in analyses
    ]

    return HistoryResponse(items=items, total=len(items))


# =============================================================================
# GET /api/analysis/{id}
# =============================================================================
@router.get(
    "/analysis/{analysis_id}",
    response_model=AnalysisResponse,
    summary="Get a single analysis by ID",
)
async def get_analysis(analysis_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found.",
        )

    return analysis.to_dict()
