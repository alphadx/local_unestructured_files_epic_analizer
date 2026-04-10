from __future__ import annotations

"""
Async SQLAlchemy engine and session factory.

Usage in FastAPI endpoints::

    from app.db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        ...

Usage in Celery workers (outside request context)::

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # SQLite doesn't support pool size settings, skip for non-PG URLs.
    **({} if settings.database_url.startswith("sqlite") else {"pool_size": 10, "max_overflow": 20}),
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """Create all tables (used on startup and in tests). For production, prefer Alembic."""
    from app.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose pooled DB connections (used during worker process shutdown)."""
    await engine.dispose()
