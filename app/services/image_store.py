# =============================================================================
# VerdaMap — Image Store Service
# =============================================================================
# Saves NDVI PNG images to disk and returns a public URL for the frontend.
#
# In production you'd swap this for S3/R2/GCS — the interface stays the same.
# =============================================================================

import uuid
import os
from pathlib import Path
from app.config import get_settings

settings = get_settings()

# Directory where images are saved — created on startup if it doesn't exist
IMAGES_DIR = Path(__file__).parent.parent.parent / "static" / "images"


def ensure_images_dir():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def save_ndvi_image(png_bytes: bytes, analysis_id: str) -> str:
    """
    Save raw PNG bytes to disk.
    Returns the public URL path (e.g. /static/images/abc123.png).
    """
    ensure_images_dir()
    filename = f"{analysis_id}.png"
    filepath = IMAGES_DIR / filename
    filepath.write_bytes(png_bytes)
    return f"/static/images/{filename}"


def delete_ndvi_image(analysis_id: str):
    """Remove the image file for a given analysis (cleanup helper)."""
    filepath = IMAGES_DIR / f"{analysis_id}.png"
    if filepath.exists():
        filepath.unlink()
