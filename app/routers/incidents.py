"""Reading incidents — the map feed and the dispatch queue.

This is the first place the pure clustering and confidence modules become visible. Up to
here they were exercised only by tests.

Note who can see what. Incidents are **public** — that is the point of the system, and a
commuter must be able to check the road ahead. Individual reports are not; those are
restricted to the control room, because showing who reported what and where is exactly
the harassment vector NFR-4 exists to prevent.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ControlRoom, CurrentUser, OptionalUser, WardenOnly
from app.confidence import THRESHOLD_STALE, THRESHOLD_VERIFIED
from app.db import get_session
from app.lifecycle import IllegalTransition, allowed_actions
from app.models import Incident, IncidentReport, IncidentStatus, IncidentType, Report, User
from app.schemas import (
    AssignRequest,
    EvidenceResponse,
    IncidentDetailResponse,
    IncidentResponse,
    ReputationChange,
    ResolveRequest,
    ResolveResponse,
    WardenResponse,
)
from app.services import dispatch

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _to_response(incident: Incident) -> IncidentResponse:
    point = to_shape(incident.centroid)
    return IncidentResponse(
        id=incident.id,
        incident_type=incident.incident_type,
        latitude=point.y,
        longitude=point.x,
        confidence=incident.confidence,
        status=incident.status,
        report_count=incident.report_count,
        first_reported_at=incident.first_reported_at,
        last_reported_at=incident.last_reported_at,
        assigned_to_id=incident.assigned_to_id,
        resolved_at=incident.resolved_at,
    )


@router.get("", response_model=list[IncidentResponse], summary="Current incidents — the map feed")
async def list_incidents(
    session: Annotated[AsyncSession, Depends(get_session)],
    incident_type: IncidentType | None = None,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = THRESHOLD_STALE,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[IncidentResponse]:
    """Open to everyone, including signed-out visitors.

    Faded incidents are excluded by default rather than deleted. Nobody closes an
    incident here — confidence decays and it drops below `min_confidence` on its own.
    Set `min_confidence=0` to see everything, including what has aged out.
    """
    stmt = (
        select(Incident)
        .where(Incident.confidence >= min_confidence)
        .where(Incident.status != IncidentStatus.RESOLVED)
        .order_by(Incident.confidence.desc(), Incident.last_reported_at.desc())
        .limit(limit)
    )
    if incident_type is not None:
        stmt = stmt.where(Incident.incident_type == incident_type)

    return [_to_response(i) for i in await session.scalars(stmt)]


@router.get(
    "/queue",
    response_model=list[IncidentResponse],
    summary="Dispatch queue — control room only",
)
async def dispatch_queue(
    _staff: ControlRoom,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IncidentResponse]:
    """What an officer acts on: incidents credible enough to be worth someone's time,
    most believable first, with anything already resolved removed."""
    rows = await session.scalars(
        select(Incident)
        .where(Incident.confidence >= THRESHOLD_VERIFIED)
        .where(Incident.status != IncidentStatus.RESOLVED)
        .order_by(Incident.confidence.desc(), Incident.last_reported_at.desc())
        .limit(limit)
    )
    return [_to_response(i) for i in rows]


@router.get(
    "/{incident_id}",
    response_model=IncidentDetailResponse,
    summary="One incident, with the evidence behind its score",
)
async def get_incident(
    incident_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    viewer: OptionalUser = None,
) -> IncidentDetailResponse:
    """The screen that makes confidence explainable.

    A number an officer cannot interrogate is a number they will learn to ignore, so the
    contributing reports are returned with the weight each one carried — which is why
    `incident_reports.weight` is stored rather than recomputed.
    """
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such incident.")

    rows = (
        await session.execute(
            select(IncidentReport, Report, User)
            .join(Report, Report.id == IncidentReport.report_id)
            .join(User, User.id == Report.reporter_id)
            .where(IncidentReport.incident_id == incident_id)
            .order_by(IncidentReport.weight.desc())
        )
    ).all()

    base = _to_response(incident)
    return IncidentDetailResponse(
        **base.model_dump(),
        evidence=[
            EvidenceResponse(
                report_id=link.report_id,
                reporter_name=user.display_name,
                reporter_reputation=user.reputation,
                occurred_at=report.occurred_at,
                weight=link.weight,
            )
            for link, report, user in rows
        ],
        # Empty for a signed-out visitor. Driving the interface from this means a button
        # that would be refused is never offered in the first place.
        allowed_actions=[
            a.value for a in allowed_actions(incident.status, viewer.role)
        ] if viewer else [],
    )


# --- dispatch -----------------------------------------------------------------


@router.get("/wardens/available", response_model=list[WardenResponse], summary="Wardens an officer can send")
async def available_wardens(
    _staff: ControlRoom,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WardenResponse]:
    return [
        WardenResponse(id=w.id, display_name=w.display_name, reputation=w.reputation)
        for w in await dispatch.wardens(session)
    ]


@router.post(
    "/{incident_id}/assign",
    response_model=IncidentResponse,
    summary="Send a warden (officer only)",
)
async def assign_warden(
    incident_id: uuid.UUID,
    body: AssignRequest,
    actor: ControlRoom,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentResponse:
    try:
        incident = await dispatch.assign(session, incident_id, actor, body.warden_id)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _to_response(incident)


@router.post(
    "/{incident_id}/unassign",
    response_model=IncidentResponse,
    summary="Recall a warden (officer only)",
)
async def unassign_warden(
    incident_id: uuid.UUID,
    actor: ControlRoom,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentResponse:
    try:
        incident = await dispatch.unassign(session, incident_id, actor)
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _to_response(incident)


@router.post(
    "/{incident_id}/resolve",
    response_model=ResolveResponse,
    summary="Close an incident (assigned warden, or an officer)",
)
async def resolve_incident(
    incident_id: uuid.UUID,
    body: ResolveRequest,
    actor: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResolveResponse:
    """The only place reputation changes.

    Everyone who reported this incident is vindicated or contradicted by what the
    warden found. The response says whose standing moved and by how much, so the
    consequence of the decision is visible rather than silent.
    """
    try:
        incident, changed = await dispatch.resolve(
            session, incident_id, actor, body.resolution, body.note
        )
    except IllegalTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return ResolveResponse(
        incident=_to_response(incident),
        reputations_updated=[
            ReputationChange(
                user_id=u.id,
                display_name=u.display_name,
                reputation=u.reputation,
                reports_confirmed=u.reports_confirmed,
                reports_contradicted=u.reports_contradicted,
            )
            for u in changed
        ],
    )


@router.get(
    "/assigned/mine",
    response_model=list[IncidentResponse],
    summary="Incidents assigned to you (warden)",
)
async def my_assignments(
    warden: WardenOnly,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[IncidentResponse]:
    rows = await session.scalars(
        select(Incident)
        .where(
            Incident.assigned_to_id == warden.id,
            Incident.status == IncidentStatus.ASSIGNED,
        )
        .order_by(Incident.confidence.desc())
    )
    return [_to_response(i) for i in rows]
