# =============================================================================
# VerdaMap — Database Setup
# =============================================================================
# Supports both SQLite (local dev, zero setup) and PostgreSQL (production).
# The driver is chosen automatically based on the DATABASE_URL prefix:
#   sqlite+aiosqlite://  → local development
#   postgresql+asyncpg:// → production
# =============================================================================

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings


settings = get_settings()

# Build engine kwargs — SQLite doesn't support pool_size / max_overflow
_is_sqlite = settings.database_url.startswith("sqlite")

_engine_kwargs = {"echo": settings.debug}
if not _is_sqlite:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    })

# Create the async engine
engine = create_async_engine(settings.database_url, **_engine_kwargs)

# Session factory — call this to get a database session
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,    # keep objects usable after commit
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db():
    """
    FastAPI dependency that provides a database session per request.
    The session is automatically closed when the request finishes.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    """Create all tables defined in models. Called on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
