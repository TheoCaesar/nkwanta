"""Clearing incidents that nobody ever confirmed.

There is a defect this module exists to fix, and it is worth stating plainly because it
was not obvious until the advisory was built.

**Confidence is computed when reports arrive, and stored.** It does not decay in the
database — decay is applied at the moment of calculation, and calculation only happens
during a rebuild, which only happens when a new report lands nearby.

So an incident reported once at 07:00 and never mentioned again keeps its 07:00
confidence forever. It sits on the map at 0.22 at midnight, hours after it decayed to
nothing in principle. The decay described in explainer 04 is real in the arithmetic and
was never applied to anything sitting still.

Two ways to fix it. Recompute on every read, which makes the map query expensive and
non-deterministic. Or sweep periodically, which is what this does: every few minutes the
worker asks which incidents have gone quiet long enough to have faded, writes their
decayed confidence down, and tells anyone who was warned that the road is clear.

The sweep uses **time since the newest report** rather than recomputing the full
noisy-OR. After eight half-lives — six hours at the default — even the strongest possible
single contribution has decayed by a factor of 256, which is below the stale threshold
from any starting point. It is an approximation, it errs on the side of keeping incidents
slightly too long, and that is the right direction to err.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.confidence import THRESHOLD_STALE, decay_factor
from app.lifecycle import COMPUTED_STATES
from app.models import Incident, IncidentStatus, OutboxMessage
from app.services.advisory import EVENT_INCIDENT_CLEARED, ClearanceReason

# Eight half-lives. At the default 45 minutes that is six hours, by which point any
# single report's contribution has shrunk by a factor of 256.
STALE_AFTER_HALF_LIVES = 8

# How often the worker checks. Cheap — one indexed query over incidents that are not
# already resolved.
SWEEP_INTERVAL_SECONDS = 300


@dataclass(frozen=True)
class SweepResult:
    examined: int
    cleared: int


async def sweep(
    session: AsyncSession,
    half_life_minutes: float,
    now: dt.datetime | None = None,
) -> SweepResult:
    """Fade out incidents nobody confirmed, and tell whoever was warned.

    Only touches incidents in a **computed** state. An incident an officer has assigned
    is a human decision, and a warden already at the junction must not be stood down
    because the reports that summoned them decayed — see the state machine in
    explainer 06.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(minutes=half_life_minutes * STALE_AFTER_HALF_LIVES)

    candidates = (
        await session.scalars(
            select(Incident).where(
                Incident.status.in_(COMPUTED_STATES),
                Incident.last_reported_at < cutoff,
                Incident.confidence >= THRESHOLD_STALE,
            )
        )
    ).all()

    cleared = 0
    for incident in candidates:
        age_minutes = (now - incident.last_reported_at).total_seconds() / 60.0
        faded = incident.confidence * decay_factor(age_minutes, half_life_minutes)

        # Write the decayed value down, so the map filter and the dispatch queue both
        # see the truth rather than a figure frozen at the last report.
        incident.confidence = faded
        incident.status = IncidentStatus.REPORTED

        await session.execute(
            pg_insert(OutboxMessage)
            .values(
                id=uuid.uuid4(),
                aggregate_type="incident",
                aggregate_id=incident.id,
                event_type=EVENT_INCIDENT_CLEARED,
                payload={
                    "incident_key": str(incident.cluster_key),
                    "incident_type": incident.incident_type.value,
                    "reason": ClearanceReason.EXPIRED.value,
                },
                idempotency_key=f"{EVENT_INCIDENT_CLEARED}:{incident.cluster_key}",
            )
            .on_conflict_do_nothing(constraint="uq_outbox_idempotency_key")
        )
        cleared += 1

    if candidates:
        await session.commit()

    return SweepResult(examined=len(candidates), cleared=cleared)
