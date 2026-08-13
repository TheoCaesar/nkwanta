"""Building incidents from reports — the projector.

`clustering.py` and `confidence.py` are pure: give them reports, they return groupings
and scores. Neither knows the database exists. This module is the bridge — it fetches
the right reports, calls those pure functions, and writes the result down.

That separation is deliberate. All the interesting logic sits in functions that can be
tested exhaustively with generated data; this file holds only the plumbing, which is the
part that needs a real database to test.


WHY REBUILD RATHER THAN UPDATE
------------------------------
When a report arrives we do not try to work out which incident it should join. We throw
away the affected incidents and rebuild them from their reports.

That sounds wasteful. It is the only correct option, because a new report can *merge*
two incidents that were previously separate — the three-in-a-line case from the
clustering explainer. An algorithm that only ever adds a report to an existing incident
can never discover that two of them are now one.

Rebuilding is also what makes the replay property true: the incident table is derived
data, and can always be reconstructed from the reports alone.


THE NEIGHBOURHOOD
-----------------
Rebuilding *everything* on every report would be correct and far too slow. So we rebuild
only the part that could have changed:

1. reports of the same type near the new one in space and time
2. plus every report belonging to any incident those reports belong to

Step 2 is easy to miss and essential. Without it, pulling in half of an existing
incident would split it — the other half would be absent from the working set and
would vanish. Expanding to whole incidents keeps the operation closed.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from geoalchemy2.functions import ST_DWithin
from geoalchemy2.shape import to_shape
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clustering import Cluster, ReportPoint, cluster_reports
from app.confidence import score, status_for
from app.config import Settings
from app.models import Incident, IncidentReport, IncidentStatus, OutboxMessage, Report, User
from app.services.advisory import ADVISORY_THRESHOLD, EVENT_INCIDENT_ADVISORY
from app.services.attachments import report_ids_with_evidence

# Reports outside the clustering radius can still end up in the same incident, linked
# through a chain of intermediate reports. Fetching a wider neighbourhood than the
# radius catches most such chains. It is a heuristic, not a guarantee — see TD-16.
NEIGHBOURHOOD_MULTIPLIER = 3


@dataclass(frozen=True)
class RebuildOutcome:
    incidents_removed: int
    incidents_written: int
    reports_considered: int


@dataclass(frozen=True)
class _Preserved:
    """Decisions a human made, which arithmetic must not overwrite.

    An incident that an officer has assigned to a warden must still be assigned after a
    rebuild. Clustering and confidence can compute the first three lifecycle states;
    `assigned` and `resolved` are human acts and are carried across.
    """

    status: IncidentStatus
    assigned_to_id: uuid.UUID | None
    resolved_at: dt.datetime | None
    resolution: str | None
    resolution_note: str | None


async def _fetch_neighbourhood(
    session: AsyncSession, seed: Report, settings: Settings
) -> list[Report]:
    radius = settings.cluster_radius_metres * NEIGHBOURHOOD_MULTIPLIER
    window = dt.timedelta(minutes=settings.cluster_window_minutes * NEIGHBOURHOOD_MULTIPLIER)

    # Step 1 — same type, near in space and time. ST_DWithin on a geography column
    # measures in metres and uses the GiST index.
    nearby = (
        await session.scalars(
            select(Report).where(
                Report.incident_type == seed.incident_type,
                Report.occurred_at.between(seed.occurred_at - window, seed.occurred_at + window),
                ST_DWithin(Report.location, seed.location, radius),
            )
        )
    ).all()

    ids = {r.id for r in nearby} | {seed.id}

    # Step 2 — expand to whole incidents. Without this a rebuild could take half an
    # incident and silently drop the other half.
    incident_ids = (
        await session.scalars(
            select(IncidentReport.incident_id).where(IncidentReport.report_id.in_(ids))
        )
    ).all()

    if incident_ids:
        sibling_ids = (
            await session.scalars(
                select(IncidentReport.report_id).where(
                    IncidentReport.incident_id.in_(set(incident_ids))
                )
            )
        ).all()
        missing = set(sibling_ids) - ids
        if missing:
            siblings = (
                await session.scalars(select(Report).where(Report.id.in_(missing)))
            ).all()
            nearby = [*nearby, *siblings]
            ids |= missing

    by_id = {r.id: r for r in nearby}
    by_id[seed.id] = seed
    return list(by_id.values())


def _to_points(reports: list[Report]) -> list[ReportPoint]:
    points = []
    for r in reports:
        shape = to_shape(r.location)
        points.append(
            ReportPoint(
                id=r.id,
                incident_type=r.incident_type.value,
                latitude=shape.y,      # shapely is (x, y) = (lon, lat) — see app/geo.py
                longitude=shape.x,
                occurred_at=r.occurred_at,
            )
        )
    return points


async def rebuild_for_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    settings: Settings,
    now: dt.datetime | None = None,
) -> RebuildOutcome:
    """Recompute every incident that this report could have affected.

    Called by the outbox worker. Does not commit — the caller owns the transaction, so
    that marking the outbox row processed and writing the incidents happen together.
    """
    now = now or dt.datetime.now(dt.timezone.utc)

    seed = await session.get(Report, report_id)
    if seed is None:
        # The report was deleted between enqueue and processing. Nothing to rebuild,
        # and not an error worth retrying.
        return RebuildOutcome(0, 0, 0)

    reports = await _fetch_neighbourhood(session, seed, settings)
    report_by_id = {r.id: r for r in reports}

    affected_incident_ids = set(
        (
            await session.scalars(
                select(IncidentReport.incident_id).where(
                    IncidentReport.report_id.in_(report_by_id.keys())
                )
            )
        ).all()
    )

    # Capture human decisions before demolishing anything, keyed by the cluster key —
    # the smallest member id, which is stable across rebuilds because membership is
    # order-independent.
    preserved: dict[uuid.UUID, _Preserved] = {}
    if affected_incident_ids:
        existing = (
            await session.scalars(
                select(Incident).where(Incident.id.in_(affected_incident_ids))
            )
        ).all()
        for inc in existing:
            member_ids = (
                await session.scalars(
                    select(IncidentReport.report_id).where(
                        IncidentReport.incident_id == inc.id
                    )
                )
            ).all()
            if member_ids and inc.status in (IncidentStatus.ASSIGNED, IncidentStatus.RESOLVED):
                preserved[min(member_ids)] = _Preserved(
                    status=inc.status,
                    assigned_to_id=inc.assigned_to_id,
                    resolved_at=inc.resolved_at,
                    resolution=inc.resolution,
                    resolution_note=inc.resolution_note,
                )

        await session.execute(delete(Incident).where(Incident.id.in_(affected_incident_ids)))

    clusters: list[Cluster] = cluster_reports(
        _to_points(reports),
        radius_metres=settings.cluster_radius_metres,
        window_minutes=settings.cluster_window_minutes,
    )

    # One query for every reputation needed, rather than one per report.
    reporter_ids = {r.reporter_id for r in reports}
    reputations = dict(
        (
            await session.execute(
                select(User.id, User.reputation).where(User.id.in_(reporter_ids))
            )
        ).all()
    )

    # One query for the whole neighbourhood rather than one per report. Reports carrying
    # a voice note or photograph weigh slightly more — see confidence.EVIDENCE_BONUS.
    with_evidence = await report_ids_with_evidence(session, list(report_by_id.keys()))

    written = 0
    for cluster in clusters:
        scored = score(
            [
                (
                    m.id,
                    reputations.get(report_by_id[m.id].reporter_id, 0.5),
                    m.occurred_at,
                )
                for m in cluster.members
            ],
            now=now,
            half_life_minutes=settings.confidence_half_life_minutes,
            with_recorded_evidence=with_evidence,
        )

        carried = preserved.get(cluster.key)
        incident = Incident(
            id=uuid.uuid4(),
            cluster_key=cluster.key,
            incident_type=report_by_id[cluster.members[0].id].incident_type,
            centroid=f"POINT({cluster.centroid_longitude} {cluster.centroid_latitude})",
            first_reported_at=cluster.first_occurred_at,
            last_reported_at=cluster.last_occurred_at,
            confidence=scored.confidence,
            report_count=cluster.size,
            status=carried.status if carried else IncidentStatus(status_for(scored.confidence)),
            assigned_to_id=carried.assigned_to_id if carried else None,
            resolved_at=carried.resolved_at if carried else None,
            resolution=carried.resolution if carried else None,
            resolution_note=carried.resolution_note if carried else None,
        )
        session.add(incident)
        await session.flush()      # need incident.id for the join rows

        for ev in scored.evidence:
            session.add(
                IncidentReport(
                    incident_id=incident.id,
                    report_id=ev.report_id,
                    # Stored, not recomputed on read, so an officer can be shown WHY
                    # confidence is what it is rather than asked to trust a number.
                    weight=ev.weight,
                )
            )
        written += 1

        # Believable enough to be worth warning commuters about? Queue an advisory.
        #
        # Only ONE row is written, however many people follow the road. The fan-out is
        # the worker's job — doing it here would make report submission slow in
        # proportion to a corridor's popularity, so the system would be slowest exactly
        # when an incident matters most.
        #
        # No "did it already cross the threshold?" check is needed. The idempotency key
        # is derived from the stable cluster key, so a repeat is refused by the unique
        # constraint. ON CONFLICT DO NOTHING keeps that from aborting the transaction.
        if scored.confidence >= ADVISORY_THRESHOLD:
            await session.execute(
                pg_insert(OutboxMessage)
                .values(
                    id=uuid.uuid4(),
                    aggregate_type="incident",
                    aggregate_id=incident.id,
                    event_type=EVENT_INCIDENT_ADVISORY,
                    payload={
                        "incident_key": str(cluster.key),
                        "incident_type": incident.incident_type.value,
                        "confidence": scored.confidence,
                    },
                    idempotency_key=f"{EVENT_INCIDENT_ADVISORY}:{cluster.key}",
                )
                .on_conflict_do_nothing(constraint="uq_outbox_idempotency_key")
            )

    return RebuildOutcome(
        incidents_removed=len(affected_incident_ids),
        incidents_written=written,
        reports_considered=len(reports),
    )
