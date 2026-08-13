"""Submitting and reading reports.

Thin on purpose. The router does HTTP; `app/services/reports.py` does the thinking.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ControlRoom, CurrentUser
from app.db import get_session
from app.models import Report
from app.schemas import ReportAccepted, ReportCreate, ReportResponse
from app.services.reports import ReportRejected, submit_report

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_response(report: Report) -> ReportResponse:
    """Geography column back out to plain numbers.

    `to_shape` gives a Shapely point whose .x is longitude and .y is latitude —
    the (x, y) convention again. See app/geo.py.
    """
    point = to_shape(report.location)
    return ReportResponse(
        id=report.id,
        incident_type=report.incident_type,
        latitude=point.y,
        longitude=point.x,
        occurred_at=report.occurred_at,
        received_at=report.received_at,
        note=report.note,
        reporter_id=report.reporter_id,
    )


@router.post(
    "",
    response_model=ReportAccepted,
    status_code=status.HTTP_201_CREATED,
    summary="Report something blocking the road",
)
async def create_report(
    body: ReportCreate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReportAccepted:
    """Any signed-in user may report. Reporting is the one thing everybody can do —
    the system is worthless if the people who can see the problem cannot tell it."""
    try:
        result = await submit_report(session, user, body)
    except ReportRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return ReportAccepted(report=_to_response(result.report), duplicate=result.duplicate)


@router.get("/mine", response_model=list[ReportResponse], summary="Your own reports")
async def my_reports(
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReportResponse]:
    rows = await session.scalars(
        select(Report)
        .where(Report.reporter_id == user.id)
        .order_by(Report.received_at.desc())
        .limit(limit)
    )
    return [_to_response(r) for r in rows]


@router.get(
    "",
    response_model=list[ReportResponse],
    summary="All recent reports (control room only)",
)
async def list_reports(
    _staff: ControlRoom,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReportResponse]:
    """Raw reports are restricted. A commuter sees incidents on the map, not other
    people's individual submissions — that would expose who reported what and where,
    which is the harassment vector NFR-4 exists to prevent."""
    rows = await session.scalars(
        select(Report).order_by(Report.received_at.desc()).limit(limit)
    )
    return [_to_response(r) for r in rows]
