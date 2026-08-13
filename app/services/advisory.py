"""Warning the people who are heading that way.

This is the first place the outbox delivers something a *user* can see. Until now it has
been faithfully carrying instructions that only rebuilt internal state.

    incident crosses the advisory threshold
        └─▶ projection writes ONE outbox row               (cheap, in the same transaction)
                └─▶ worker matches corridors and fans out  (expensive, in the background)
                        └─▶ one notification per subscriber


WHY THE FAN-OUT HAPPENS IN THE WORKER
-------------------------------------
The projector could look up subscribers itself. It must not.

A busy corridor might have thousands of followers. Doing that work inside the request
that accepted a report would make submission slow in proportion to how popular the road
is — the system would be slowest exactly when an incident matters most.

So the projector writes one small row saying "this incident deserves an advisory", and
the worker turns that into however many notifications it needs to. Submission stays fast
and constant-time; the expensive part happens where being slow is harmless.


WHY COMMUTERS ARE WARNED EARLIER THAN POLICE ARE CALLED
------------------------------------------------------
Advisory fires at **0.35** (corroborated). Dispatch requires **0.70** (verified).

Not an inconsistency — the two decisions have different costs. Sending a warden to
nothing wastes a person who was needed elsewhere. Telling a commuter about something
that turns out to be clear costs them a glance at the map. When the price of being wrong
differs by that much, the threshold should differ too.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from dataclasses import dataclass

from geoalchemy2.functions import ST_DWithin
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.confidence import THRESHOLD_CORROBORATED
from app.models import (
    Corridor,
    CorridorSubscription,
    Incident,
    IncidentType,
    Notification,
)

EVENT_INCIDENT_ADVISORY = "incident.advisory"
EVENT_INCIDENT_CLEARED = "incident.cleared"


class ClearanceReason(str, enum.Enum):
    """Why a road stopped being a problem. The three cases read differently to a
    commuter and are worth distinguishing."""

    RESOLVED = "resolved"          # someone attended and the road is clear
    FALSE_ALARM = "false_alarm"    # someone attended and found nothing
    EXPIRED = "expired"            # nobody ever confirmed it, and it aged out

# How close an incident must be to a road before it counts as "on" that road. Generous
# enough to catch an incident on the far carriageway or just off a junction, tight
# enough that a parallel street does not trigger it. Another guess with no data behind
# it — see TD-03.
CORRIDOR_MATCH_METRES = 250

ADVISORY_THRESHOLD = THRESHOLD_CORROBORATED

_HUMAN_TYPE = {
    IncidentType.ACCIDENT: "An accident",
    IncidentType.FLOOD: "Flooding",
    IncidentType.CLOSURE: "A road closure",
    IncidentType.SIGNAL_OUTAGE: "Traffic lights out",
    IncidentType.ROADWORKS: "Roadworks",
    IncidentType.SURFACE_DEFECT: "A damaged road surface",
}


@dataclass(frozen=True)
class FanOutResult:
    corridors_matched: int
    notifications_created: int


def compose_message(incident_type: IncidentType, corridor_name: str, confidence: float) -> str:
    """What the commuter actually reads.

    Confidence is expressed in words rather than as a number. "0.42" means nothing to
    someone deciding whether to leave early; "reported by several people" does. The
    number is still available on the incident itself for anyone who wants it.
    """
    strength = (
        "confirmed by several people" if confidence >= 0.70
        else "reported by more than one person" if confidence >= 0.50
        else "reported, not yet confirmed"
    )
    return f"{_HUMAN_TYPE[incident_type]} on {corridor_name} — {strength}."


async def matching_corridors(
    session: AsyncSession, incident: Incident, metres: int = CORRIDOR_MATCH_METRES
) -> list[Corridor]:
    """Which followed roads this incident sits on.

    `ST_DWithin` against a LINESTRING geography measures the distance to the *nearest
    point on the line*, in metres, using the GiST index. That is exactly the question —
    a corridor modelled as a centre point with a radius could not answer it.
    """
    rows = await session.scalars(
        select(Corridor).where(
            Corridor.is_active.is_(True),
            ST_DWithin(Corridor.path, incident.centroid, metres),
        )
    )
    return list(rows)


async def fan_out(
    session: AsyncSession,
    incident_key: uuid.UUID,
    incident: Incident,
) -> FanOutResult:
    """Turn one advisory into one notification per affected subscriber.

    Does not commit — the worker owns the transaction, so the notifications and the
    "processed" mark on the outbox row land together.
    """
    corridors = await matching_corridors(session, incident)
    if not corridors:
        return FanOutResult(0, 0)

    corridor_by_id = {c.id: c for c in corridors}

    subscriptions = (
        await session.scalars(
            select(CorridorSubscription).where(
                CorridorSubscription.corridor_id.in_(corridor_by_id.keys())
            )
        )
    ).all()
    if not subscriptions:
        return FanOutResult(len(corridors), 0)

    # A commuter following two roads that both pass the incident is one person, and
    # should hear once. Keep the first corridor seen so the message can name a road.
    first_corridor_for_user: dict[uuid.UUID, uuid.UUID] = {}
    for sub in subscriptions:
        first_corridor_for_user.setdefault(sub.user_id, sub.corridor_id)

    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "incident_key": incident_key,
            "corridor_id": corridor_id,
            "incident_type": incident.incident_type,
            "message": compose_message(
                incident.incident_type,
                corridor_by_id[corridor_id].name,
                incident.confidence,
            ),
            "confidence": incident.confidence,
        }
        for user_id, corridor_id in first_corridor_for_user.items()
    ]

    # ON CONFLICT DO NOTHING against the (user_id, incident_key) constraint.
    #
    # This is what makes at-least-once delivery survivable. The worker may replay this
    # advisory after a crash, a retry, or a rebuild, and the recipient is still warned
    # exactly once. Catching an IntegrityError instead would abort the surrounding
    # transaction and take the rest of the batch with it.
    result = await session.execute(
        pg_insert(Notification)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_notifications_once_per_incident")
    )

    return FanOutResult(corridors_matched=len(corridors), notifications_created=result.rowcount or 0)


# --- clearance ----------------------------------------------------------------


_CLEARANCE_WORDING = {
    ClearanceReason.RESOLVED: "{what} on {road} has been cleared.",
    ClearanceReason.FALSE_ALARM: "{what} reported on {road} could not be found — the road is clear.",
    ClearanceReason.EXPIRED: "{what} reported on {road} was never confirmed and has been removed.",
}


def compose_clearance(
    incident_type: IncidentType, corridor_name: str, reason: ClearanceReason
) -> str:
    what = _HUMAN_TYPE[incident_type]
    return _CLEARANCE_WORDING[reason].format(what=what, road=corridor_name)


async def fan_out_clearance(
    session: AsyncSession,
    incident_key: uuid.UUID,
    incident_type: IncidentType,
    reason: ClearanceReason,
) -> int:
    """Tell the people who were warned that the road is clear again.

    **The audience is exactly the audience of the original warning**, taken from the
    notifications already sent rather than recomputed from corridors. That matters for
    two reasons.

    It guarantees consistency: nobody is told a road has cleared when they were never
    told it was blocked. And it survives change — if the corridor was edited, or the
    incident's centroid moved as reports accumulated, recomputing would reach a
    different set of people and some commuters would be left believing a road is still
    blocked.

    A system that reports blockages and never reports clearances trains people to
    ignore it. That is why this exists.
    """
    prior = (
        await session.scalars(
            select(Notification).where(Notification.incident_key == incident_key)
        )
    ).all()
    if not prior:
        return 0

    corridor_names = dict(
        (
            await session.execute(
                select(Corridor.id, Corridor.name).where(
                    Corridor.id.in_({n.corridor_id for n in prior if n.corridor_id})
                )
            )
        ).all()
    )

    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": n.user_id,
            # A distinct key from the advisory, so the clearance is a second
            # notification rather than being swallowed by the "warned once" constraint.
            "incident_key": _clearance_key(incident_key),
            "corridor_id": n.corridor_id,
            "incident_type": incident_type,
            "message": compose_clearance(
                incident_type,
                corridor_names.get(n.corridor_id, "your route"),
                reason,
            ),
            "confidence": 0.0,
        }
        for n in prior
        if n.incident_key == incident_key      # skip any clearance rows already present
    ]
    if not rows:
        return 0

    result = await session.execute(
        pg_insert(Notification)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_notifications_once_per_incident")
    )
    return result.rowcount or 0


def _clearance_key(incident_key: uuid.UUID) -> uuid.UUID:
    """A derived key so a clearance is one notification per person, separate from the
    warning but equally idempotent.

    Deterministic, so replaying the clearance produces the same key and the unique
    constraint refuses the duplicate.
    """
    return uuid.uuid5(uuid.NAMESPACE_OID, f"cleared:{incident_key}")
