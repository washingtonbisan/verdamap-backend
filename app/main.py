# =============================================================================
# VerdaMap — FastAPI Application Entry Point
# =============================================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import get_settings
from app.database import create_tables
from app.routers.analysis import router as analysis_router
from app.schemas import HealthCheckResponse

settings = get_settings()

# =============================================================================
# Lifespan — runs on startup and shutdown
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    # Create DB tables if they don't exist yet
    await create_tables()

    # Ensure the static/images directory exists
    images_dir = Path(__file__).parent.parent / "static" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print("✅ VerdaMap API is ready.")
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    print("👋 VerdaMap API shutting down.")


# =============================================================================
# App instance
# =============================================================================
app = FastAPI(
    title="VerdaMap API",
    description="NDVI vegetation analysis powered by Sentinel-2 satellite imagery.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",     # ReDoc at /redoc
)

# =============================================================================
# CORS — allow the frontend to call the API
# =============================================================================
origins = [o.strip().rstrip("/") for o in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Static files — serve NDVI images at /static/images/<filename>
# =============================================================================
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# =============================================================================
# Routes
# =============================================================================
app.include_router(analysis_router)


@app.get("/health", response_model=HealthCheckResponse, tags=["system"])
async def health_check():
    """Simple liveness check — returns 200 if the server is running."""
    return HealthCheckResponse(status="ok", version="1.0.0")
