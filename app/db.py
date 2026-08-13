"""Database engine and session handling.

The engine is created lazily. If DATABASE_URL is not set the application still starts
and /health reports the database as "not configured" rather than crashing on import.
That is deliberate -- the first Render deploy happens before Neon is connected.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Parent class for every table in the system."""


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_configured:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy .env.example to .env and paste your "
                "Neon connection string into it."
            )
        _engine = create_async_engine(
            settings.sqlalchemy_url,
            echo=False,
            pool_pre_ping=True,   # Neon closes idle connections; re-check before use
            pool_size=5,          # free tier is small -- do not be greedy
            max_overflow=2,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. One session per request, always closed."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
