"""Following roads, and reading the warnings that follow.

The commuter half of the product. Everything before this served the control room; this
is what a member of the public gets in return for reporting.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.db import get_session
from app.models import Corridor, CorridorSubscription, Notification
from app.schemas import CorridorResponse, NotificationResponse

router = APIRouter(tags=["corridors and advisories"])


@router.get("/corridors", response_model=list[CorridorResponse], summary="Roads you can follow")
async def list_corridors(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CorridorResponse]:
    """A curated list, not a map to draw on.

    Drawing your own route needs a routing engine and full network data. Fifteen named
    Accra roads cover most journeys and could be built now — recorded in the backlog
    rather than pretended to be a design preference.
    """
    followed = set(
        await session.scalars(
            select(CorridorSubscription.corridor_id).where(
                CorridorSubscription.user_id == user.id
            )
        )
    )
    rows = await session.scalars(
        select(Corridor).where(Corridor.is_active.is_(True)).order_by(Corridor.name)
    )
    return [
        CorridorResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            following=c.id in followed,
        )
        for c in rows
    ]


@router.put(
    "/corridors/{corridor_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Follow a road",
)
async def follow(
    corridor_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """PUT, not POST, because following twice should mean the same as following once.

    The insert ignores a conflict rather than erroring, so a client that retries on a
    flaky connection is not punished for it.
    """
    if await session.get(Corridor, corridor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such corridor.")

    await session.execute(
        pg_insert(CorridorSubscription)
        .values(user_id=user.id, corridor_id=corridor_id)
        .on_conflict_do_nothing()
    )
    await session.commit()


@router.delete(
    "/corridors/{corridor_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop following a road",
)
async def unfollow(
    corridor_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await session.execute(
        delete(CorridorSubscription).where(
            CorridorSubscription.user_id == user.id,
            CorridorSubscription.corridor_id == corridor_id,
        )
    )
    await session.commit()


@router.get(
    "/notifications",
    response_model=list[NotificationResponse],
    summary="Warnings about roads you follow",
)
async def my_notifications(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NotificationResponse]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    rows = await session.scalars(stmt)
    return [
        NotificationResponse(
            id=n.id,
            incident_key=n.incident_key,
            incident_type=n.incident_type,
            message=n.message,
            confidence=n.confidence,
            created_at=n.created_at,
            read_at=n.read_at,
        )
        for n in rows
    ]


@router.post(
    "/notifications/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all your warnings as read",
)
async def mark_read(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    from sqlalchemy import update

    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=dt.datetime.now(dt.timezone.utc))
    )
    await session.commit()


@router.get(
    "/notifications/count",
    summary="How many unread warnings you have",
)
async def unread_count(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, int]:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return {"unread": count or 0}
