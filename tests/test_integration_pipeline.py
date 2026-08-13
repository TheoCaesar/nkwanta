"""End-to-end pipeline test — requires a real PostGIS database.

Everything else in the suite runs against stubs and pure functions, which is fast and
catches most things. It cannot catch what only a real database can: whether
`ST_DWithin` is measuring metres, whether the geography column round-trips coordinates
in the right order, whether the cascade deletes behave.

So this file exercises the whole chain for real:

    POST a report -> outbox row written in the same transaction
                  -> worker claims it
                  -> neighbourhood fetched with a live PostGIS query
                  -> clustering and confidence run
                  -> incident written and readable

**Skipped automatically when DATABASE_URL is not set**, so `pytest` still passes on a
machine with no database. Run it deliberately:

    pytest tests/test_integration_pipeline.py -v

Everything it creates is deleted afterwards, including when an assertion fails.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.confidence import THRESHOLD_CORROBORATED
from app.models import (
    Incident,
    IncidentReport,
    IncidentType,
    OutboxMessage,
    Report,
    User,
    UserRole,
)
from app.schemas import ReportCreate
from app.security import hash_password
from app.services.reports import submit_report
from app.worker import OutboxWorker

pytestmark = pytest.mark.skipif(
    not get_settings().database_configured,
    reason="no DATABASE_URL configured — integration tests skipped",
)

# Kwame Nkrumah Circle. Three points within about 100 m of each other.
CIRCLE = [
    (5.60370, -0.18700),
    (5.60415, -0.18740),
    (5.60340, -0.18660),
]
# Achimota, roughly 8 km away — must never join the Circle incident.
ACHIMOTA = (5.61980, -0.22690)


@pytest.fixture
async def db():
    settings = get_settings()
    engine = create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.fixture
async def reporter(db):
    """A throwaway account, removed with everything it created."""
    marker = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        email=f"itest-{marker}@nkwanta.test",
        password_hash=hash_password("integration-test-only"),
        display_name=f"Integration {marker}",
        role=UserRole.COMMUTER,
        reputation=0.5,
    )
    async with db() as session:
        session.add(user)
        await session.commit()

    yield user

    async with db() as session:
        report_ids = list(
            await session.scalars(select(Report.id).where(Report.reporter_id == user.id))
        )
        if report_ids:
            incident_ids = list(
                await session.scalars(
                    select(IncidentReport.incident_id).where(
                        IncidentReport.report_id.in_(report_ids)
                    )
                )
            )
            if incident_ids:
                await session.execute(
                    delete(Incident).where(Incident.id.in_(set(incident_ids)))
                )
            await session.execute(
                delete(OutboxMessage).where(OutboxMessage.aggregate_id.in_(report_ids))
            )
            await session.execute(delete(Report).where(Report.id.in_(report_ids)))
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def _submit(db, reporter: User, lat: float, lon: float, minutes_ago: int = 0) -> Report:
    async with db() as session:
        user = await session.get(User, reporter.id)
        result = await submit_report(
            session,
            user,
            ReportCreate(
                incident_type=IncidentType.ACCIDENT,
                latitude=lat,
                longitude=lon,
                occurred_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago),
            ),
        )
        return result.report


async def _incidents_for(db, report_ids: list[uuid.UUID]) -> list[Incident]:
    async with db() as session:
        incident_ids = set(
            await session.scalars(
                select(IncidentReport.incident_id).where(
                    IncidentReport.report_id.in_(report_ids)
                )
            )
        )
        if not incident_ids:
            return []
        return list(
            await session.scalars(select(Incident).where(Incident.id.in_(incident_ids)))
        )


# =============================================================================


@pytest.mark.asyncio
async def test_postgis_is_actually_installed(db) -> None:
    from sqlalchemy import text

    async with db() as session:
        version = await session.scalar(text("SELECT postgis_version()"))
    assert version is not None


@pytest.mark.asyncio
async def test_submitting_a_report_writes_an_outbox_row_in_the_same_transaction(
    db, reporter
) -> None:
    report = await _submit(db, reporter, *CIRCLE[0])

    async with db() as session:
        msg = await session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == report.id)
        )

    assert msg is not None
    assert msg.processed_at is None
    assert msg.idempotency_key == f"report.submitted:{report.id}"


@pytest.mark.asyncio
async def test_three_nearby_reports_become_one_incident(db, reporter) -> None:
    """The whole pipeline, for real: three reports at Circle, one incident out."""
    reports = [await _submit(db, reporter, lat, lon) for lat, lon in CIRCLE]

    worker = OutboxWorker(db, get_settings())
    for _ in range(4):                 # one pass per report, plus slack
        if await worker.drain_once() == 0:
            break

    incidents = await _incidents_for(db, [r.id for r in reports])

    assert len(incidents) == 1, f"expected one incident, got {len(incidents)}"
    incident = incidents[0]
    assert incident.report_count == 3
    assert incident.incident_type == IncidentType.ACCIDENT
    # Three fresh reports from one reputation-0.5 account: about 0.535
    assert incident.confidence >= THRESHOLD_CORROBORATED


@pytest.mark.asyncio
async def test_a_distant_report_forms_its_own_incident(db, reporter) -> None:
    """8 km apart must never merge — proves ST_DWithin is measuring metres, which is
    the thing that silently breaks if a geometry column is used instead of geography."""
    near = await _submit(db, reporter, *CIRCLE[0])
    far = await _submit(db, reporter, *ACHIMOTA)

    worker = OutboxWorker(db, get_settings())
    for _ in range(3):
        if await worker.drain_once() == 0:
            break

    incidents = await _incidents_for(db, [near.id, far.id])
    assert len(incidents) == 2


@pytest.mark.asyncio
async def test_coordinates_survive_the_round_trip(db, reporter) -> None:
    """Latitude and longitude come back as they went in. If they were swapped on the
    way into the geography column, this incident's centroid lands in the Gulf of
    Guinea and nothing else would have noticed."""
    from geoalchemy2.shape import to_shape

    report = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    await worker.drain_once()

    incidents = await _incidents_for(db, [report.id])
    assert len(incidents) == 1

    point = to_shape(incidents[0].centroid)
    assert point.y == pytest.approx(CIRCLE[0][0], abs=1e-4)   # latitude
    assert point.x == pytest.approx(CIRCLE[0][1], abs=1e-4)   # longitude


@pytest.mark.asyncio
async def test_the_outbox_row_is_marked_processed(db, reporter) -> None:
    report = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    await worker.drain_once()

    async with db() as session:
        msg = await session.scalar(
            select(OutboxMessage).where(OutboxMessage.aggregate_id == report.id)
        )
    assert msg.processed_at is not None
    assert msg.last_error is None


@pytest.mark.asyncio
async def test_draining_twice_does_not_duplicate_incidents(db, reporter) -> None:
    """Idempotence end to end. A restart mid-batch must not double-count."""
    reports = [await _submit(db, reporter, lat, lon) for lat, lon in CIRCLE[:2]]

    worker = OutboxWorker(db, get_settings())
    for _ in range(3):
        if await worker.drain_once() == 0:
            break

    first = await _incidents_for(db, [r.id for r in reports])
    await worker.drain_once()
    second = await _incidents_for(db, [r.id for r in reports])

    assert len(first) == len(second) == 1
    assert first[0].report_count == second[0].report_count


@pytest.mark.asyncio
async def test_a_later_report_merges_into_the_existing_incident(db, reporter) -> None:
    """The case incremental assignment cannot handle: an incident must grow when a new
    report arrives near it, not spawn a second one beside it."""
    first = await _submit(db, reporter, *CIRCLE[0])

    worker = OutboxWorker(db, get_settings())
    await worker.drain_once()
    assert (await _incidents_for(db, [first.id]))[0].report_count == 1

    second = await _submit(db, reporter, *CIRCLE[1])
    await worker.drain_once()

    incidents = await _incidents_for(db, [first.id, second.id])
    assert len(incidents) == 1
    assert incidents[0].report_count == 2
