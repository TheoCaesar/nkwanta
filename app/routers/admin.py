"""Administrative endpoints.

Two of them, both admin-only, and both exist for the demonstration rather than for
production. That is stated plainly here rather than dressed up: an endpoint that wipes
and rebuilds demonstration data has no place in a real deployment, and it is recorded
as technical debt TD-17.

The reason it exists is real, though. Confidence decays with a 45-minute half-life, so
data seeded yesterday is invisible today. Before a viva or a demonstration the map needs
refreshing, and doing that from a browser is considerably more reliable than asking
someone to find a terminal.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AdminOnly
from app.db import get_session
from app.models import Incident, IncidentStatus, OutboxMessage, Report, User
from app.services.seed import clear_demo_data, seed
from app.worker import get_worker

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get("/stats", summary="What is in the database (admin only)")
async def stats(
    _admin: AdminOnly,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    async def count(model) -> int:
        return await session.scalar(select(func.count()).select_from(model)) or 0

    pending = await session.scalar(
        select(func.count()).select_from(OutboxMessage).where(
            OutboxMessage.processed_at.is_(None)
        )
    )
    verified = await session.scalar(
        select(func.count()).select_from(Incident).where(
            Incident.status == IncidentStatus.VERIFIED
        )
    )
    worker = get_worker()

    return {
        "users": await count(User),
        "reports": await count(Report),
        "incidents": await count(Incident),
        "incidents_verified": verified or 0,
        "outbox_pending": pending or 0,
        "worker_running": worker is not None,
        "worker_processed": worker.processed_count if worker else 0,
        "worker_failed": worker.failed_count if worker else 0,
    }


@router.post("/drain", summary="Process the outbox now (admin only)")
async def drain(_admin: AdminOnly) -> dict[str, Any]:
    """Force a drain instead of waiting for the next poll.

    Useful in a demonstration: submit a report, call this, and the incident appears
    immediately rather than up to two seconds later. Safe to call at any time — the
    worker is idempotent and rows already processed are skipped.
    """
    worker = get_worker()
    if worker is None:
        return {"handled": 0, "detail": "No worker is running — is DATABASE_URL set?"}

    handled = await worker.drain_once()
    return {
        "handled": handled,
        "processed_total": worker.processed_count,
        "failed_total": worker.failed_count,
    }


@router.post("/seed", summary="Refresh the demonstration data (admin only)")
async def reseed(
    _admin: AdminOnly,
    session: Annotated[AsyncSession, Depends(get_session)],
    reset: bool = True,
) -> dict[str, Any]:
    """Rebuild the demonstration data with timestamps relative to now.

    Run this shortly before a demonstration. Seeded reports go through the ordinary
    outbox, clustering and confidence path — nothing about them is special-cased, so
    what an examiner sees is produced by exactly the code that handles live reports.
    """
    if reset:
        await clear_demo_data(session)

    result = await seed(session)

    worker = get_worker()
    passes = 0
    if worker is not None:
        while passes < 20 and await worker.drain_once() > 0:
            passes += 1

    incidents = await session.scalar(select(func.count()).select_from(Incident)) or 0
    return {
        "users_created": result.users_created,
        "reports_created": result.reports_created,
        "outbox_queued": result.outbox_queued,
        "drain_passes": passes,
        "incidents_now": incidents,
    }
