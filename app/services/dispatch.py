"""Sending someone, and closing the loop afterwards.

Three operations — assign, unassign, resolve — each of which asks `lifecycle.py` whether
the move is legal before touching anything. The state machine holds the rules; this file
holds the database work.

Resolving is the interesting one. It is the only point in the whole system where
**reputation actually moves**. Everything upstream weights reports by their reporter's
standing; this is where that standing is earned or lost, based on whether someone went
and looked.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import reputation as rep
from app.lifecycle import Action, IllegalTransition, Resolution, next_status
from app.models import Incident, IncidentReport, IncidentStatus, Report, User, UserRole


class DispatchError(Exception):
    """Something about the request is wrong. The message is safe to show a user."""


async def _load(session: AsyncSession, incident_id: uuid.UUID) -> Incident:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise DispatchError("No such incident.")
    return incident


async def assign(
    session: AsyncSession,
    incident_id: uuid.UUID,
    actor: User,
    warden_id: uuid.UUID,
) -> Incident:
    """An officer sends a warden."""
    incident = await _load(session, incident_id)
    incident.status = next_status(incident.status, Action.ASSIGN, actor.role)

    warden = await session.get(User, warden_id)
    if warden is None or warden.role != UserRole.WARDEN:
        raise DispatchError("That user is not a traffic warden.")
    if not warden.is_active:
        raise DispatchError("That warden's account is not active.")

    incident.assigned_to_id = warden.id
    await session.commit()
    await session.refresh(incident)
    return incident


async def unassign(
    session: AsyncSession, incident_id: uuid.UUID, actor: User
) -> Incident:
    """Recall a warden. The incident returns to the queue at `verified`."""
    incident = await _load(session, incident_id)
    incident.status = next_status(incident.status, Action.UNASSIGN, actor.role)
    incident.assigned_to_id = None
    await session.commit()
    await session.refresh(incident)
    return incident


async def resolve(
    session: AsyncSession,
    incident_id: uuid.UUID,
    actor: User,
    resolution: Resolution,
    note: str | None = None,
    now: dt.datetime | None = None,
) -> tuple[Incident, list[User]]:
    """Close an incident and settle the reputations of everyone who reported it.

    Returns the incident and the reporters whose standing changed, so the caller can
    show what the decision cost or earned.

    A warden may only close an incident they were actually sent to. Without that check,
    any warden could clear the whole queue from a phone, and the assignment step would
    mean nothing.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    incident = await _load(session, incident_id)

    if actor.role == UserRole.WARDEN and incident.assigned_to_id != actor.id:
        raise DispatchError("You can only resolve an incident you were assigned to.")

    incident.status = next_status(incident.status, Action.RESOLVE, actor.role)
    incident.resolved_at = now
    incident.resolution = resolution.value
    incident.resolution_note = note or None

    # --- the reputation feedback loop -----------------------------------------
    reporters = (
        await session.scalars(
            select(User)
            .join(Report, Report.reporter_id == User.id)
            .join(IncidentReport, IncidentReport.report_id == Report.id)
            .where(IncidentReport.incident_id == incident.id)
            .distinct()
        )
    ).all()

    # Distinct, so filing six reports about one incident earns one confirmation rather
    # than six. Otherwise the fastest way to build reputation would be to spam.
    changed: list[User] = []
    for reporter in reporters:
        if resolution is Resolution.CONFIRMED:
            update = rep.after_confirmation(reporter.reports_confirmed, reporter.reports_contradicted)
        else:
            update = rep.after_contradiction(reporter.reports_confirmed, reporter.reports_contradicted)

        reporter.reports_confirmed = update.confirmed
        reporter.reports_contradicted = update.contradicted
        reporter.reputation = update.reputation
        changed.append(reporter)

    await session.commit()
    await session.refresh(incident)
    return incident, changed


async def wardens(session: AsyncSession) -> list[User]:
    """Active wardens, for the officer's assignment list."""
    rows = await session.scalars(
        select(User)
        .where(User.role == UserRole.WARDEN, User.is_active.is_(True))
        .order_by(User.display_name)
    )
    return list(rows)
