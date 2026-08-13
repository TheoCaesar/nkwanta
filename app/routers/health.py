"""Health and readiness endpoints.

/health   -- cheap. Never touches the database. This is what the keep-warm ping hits.
/ready    -- checks the database and PostGIS. Used once after deploy to prove wiring.

Keeping these separate matters. A keep-warm ping every ten minutes must not burn
Neon compute-hours on the free tier, and a liveness check that fails because a
dependency is down will get your service restarted for no reason.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker

router = APIRouter(tags=["operations"])

_STARTED_AT = time.time()


@router.get("/health", summary="Liveness — is the process up?")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "database_configured": settings.database_configured,
    }


@router.get("/ready", summary="Readiness — is the database reachable and PostGIS present?")
async def ready() -> dict[str, Any]:
    settings = get_settings()

    if not settings.database_configured:
        return {
            "status": "degraded",
            "database": "not configured",
            "postgis": "unknown",
            "detail": "DATABASE_URL is empty. The app is running but has no database.",
        }

    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
            row = (
                await session.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
                )
            ).first()
    except Exception as exc:  # noqa: BLE001 - surface the real reason in the response
        return {
            "status": "error",
            "database": "unreachable",
            "postgis": "unknown",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    if row is None:
        return {
            "status": "degraded",
            "database": "connected",
            "postgis": "missing",
            "detail": "Run: CREATE EXTENSION IF NOT EXISTS postgis;",
        }

    return {
        "status": "ok",
        "database": "connected",
        "postgis": row[0],
    }
