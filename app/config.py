# =============================================================================
# VerdaMap — Configuration
# =============================================================================
# All settings are read from environment variables.
# In development, these come from a .env file (loaded by python-dotenv).
# In production, set them directly in your hosting platform.
# =============================================================================

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "VerdaMap API"
    debug: bool = False

    # Comma-separated list of allowed frontend origins for CORS
    allowed_origins: str = "http://localhost:5173"

    # Public base URL of THIS backend server (used to build image URLs)
    # In production set this to e.g. https://api.yourdomain.com
    api_base_url: str = "http://localhost:8000"

    # ── Database ─────────────────────────────────────────────────────────────
    # SQLite for local dev (zero setup), PostgreSQL for production
    # sqlite+aiosqlite:///./verdamap.db  ← local
    # postgresql+asyncpg://user:pass@host:5432/dbname  ← production
    database_url: str = "sqlite+aiosqlite:///./verdamap.db"

    # ── Sentinel Hub ─────────────────────────────────────────────────────────
    # Get these from: https://apps.sentinel-hub.com/dashboard/#/account/settings
    # Click "OAuth clients" → "Create new"
    sentinelhub_client_id: str = ""
    sentinelhub_client_secret: str = ""

    # Sentinel Hub API endpoints (Copernicus Data Space)
    sentinelhub_token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
        "/protocol/openid-connect/token"
    )
    sentinelhub_process_url: str = "https://sh.dataspace.copernicus.eu/api/v1/process"
    sentinelhub_statistics_url: str = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — only reads .env once."""
    return Settings()
