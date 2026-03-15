"""Async SQLAlchemy engine and session factory for PostgreSQL."""

from __future__ import annotations

import os
from typing import AsyncIterator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bundle_analyzer.db.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_database_url() -> str:
    """Resolve the database URL from environment variables.

    Supports DATABASE_URL (Railway sets this automatically) with
    automatic postgres:// -> postgresql+asyncpg:// conversion.

    Returns:
        Async-compatible database URL string.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL or POSTGRES_URL environment variable is not set. "
            "Add a PostgreSQL database to your Railway project."
        )
    # Railway provides postgres:// but asyncpg needs postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_db() -> None:
    """Initialize the database engine, create tables if needed."""
    global _engine, _session_factory

    url = _get_database_url()
    _engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized successfully")


async def close_db() -> None:
    """Dispose of the database engine on shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database connection closed")


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async database session.

    Yields:
        An AsyncSession for database operations.
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session
